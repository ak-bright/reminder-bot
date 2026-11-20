"""Natural-language parser: plain message -> ParsedMessage, using the cheap model (Haiku).

Uses structured outputs (`messages.parse`), so the reply is already validated
against our pydantic schema. Token usage is logged on every call (CLAUDE.md rule 9).
"""

from datetime import datetime
from typing import Protocol

import anthropic

from reminderbot.ai.prompts import PARSER_SYSTEM, parser_user_content
from reminderbot.ai.schemas import ParsedMessage
from reminderbot.logging_setup import get_logger

log = get_logger(__name__)

MAX_ITEMS = 10  # more tasks than this in one message is almost certainly a mistake


class ParserError(Exception):
    """The AI couldn't give us a usable answer (network, API error, refusal, ...)."""


class MessageParser(Protocol):
    """What the bot needs. Tests pass a fake that returns ready-made answers."""

    async def parse(self, text: str, now_local: datetime, timezone: str) -> ParsedMessage: ...


class ClaudeParser:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str, max_output_tokens: int):
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens

    async def parse(self, text: str, now_local: datetime, timezone: str) -> ParsedMessage:
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=PARSER_SYSTEM,
                messages=[
                    {"role": "user", "content": parser_user_content(text, now_local, timezone)}
                ],
                output_format=ParsedMessage,
                # Parsing is easy, so think as little as possible (cheaper and faster).
                output_config={"effort": "low"},
            )
        except anthropic.APIConnectionError as error:
            raise ParserError("could not reach the API") from error
        except anthropic.APIStatusError as error:
            # 400 = our request is wrong, 429/5xx = busy (the SDK already retried twice).
            log.warning("ai_error", purpose="parse", status=error.status_code)
            raise ParserError(f"API error {error.status_code}") from error
        except anthropic.AnthropicError as error:
            # E.g. the answer didn't match the schema. Never trust half-valid output.
            raise ParserError("unusable answer") from error

        usage = response.usage
        log.info(
            "ai_usage",
            purpose="parse",
            model=self._model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            stop_reason=response.stop_reason,
        )
        parsed = response.parsed_output
        if response.stop_reason != "end_turn" or parsed is None:
            # "refusal" or "max_tokens" (cut off): there is no complete answer.
            raise ParserError(f"no answer (stop_reason={response.stop_reason})")
        return clean(parsed)


def clean(parsed: ParsedMessage) -> ParsedMessage:
    """Final checks on the model's answer before the rest of the bot uses it."""
    if parsed.intent != "reminder":
        return ParsedMessage(intent=parsed.intent, items=[])
    items = []
    for item in parsed.items[:MAX_ITEMS]:
        title = " ".join(item.title.split())[:200]  # tidy spaces, respect the DB limit
        confidence = min(max(item.confidence, 0.0), 1.0)
        items.append(item.model_copy(update={"title": title, "confidence": confidence}))
    return ParsedMessage(intent="reminder", items=items)
