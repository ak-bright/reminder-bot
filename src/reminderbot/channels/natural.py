"""Plain-language messages ("DS assignment due Friday 5pm") -> reminders (M4).

Flow for each message:
  1. The AI parser describes the tasks and times (ai/parser.py).
  2. Our own code works out the exact moment (core/when.py).
  3. Clear items are saved and confirmed straight away.
  4. Unclear items wait in a queue; we ask about them ONE question at a time,
     with buttons, and the user can also type the answer (CLAUDE.md rule 5).
"""

import asyncio
from datetime import timedelta
from zoneinfo import ZoneInfo

from reminderbot.ai.parser import MessageParser, ParserError
from reminderbot.ai.schemas import ParsedItem, ParsedMessage
from reminderbot.channels.base import Button, Channel, IncomingEvent
from reminderbot.channels.replies import send_confirmation
from reminderbot.clock import Clock
from reminderbot.core.clarify import Clarification, ClarificationStore, PendingReminder
from reminderbot.core.crosscheck import dates_agree, worth_checking
from reminderbot.core.formatting import format_datetime
from reminderbot.core.models import ReminderKind
from reminderbot.core.reminders import ReminderInfo, ReminderService
from reminderbot.core.users import UserProfile
from reminderbot.core.when import Ask, Resolved, WhenSpec, describe_choice, resolve
from reminderbot.logging_setup import get_logger
from reminderbot.strings import t

log = get_logger(__name__)

# Button data: "cl:<question token>:<choice number>", or "cl:<token>:x" for Cancel.
CLARIFY_PREFIX = "cl:"
CANCEL = "x"
CLARIFY_TTL = timedelta(hours=1)  # an unanswered question goes away after this
# Below this, we show the AI's answer and ask the user to confirm it.
CONFIDENCE_THRESHOLD = 0.7


class NaturalLanguage:
    def __init__(
        self,
        parser: MessageParser | None,
        reminders: ReminderService,
        clarifications: ClarificationStore,
        clock: Clock,
        max_input_chars: int,
    ) -> None:
        self._parser = parser  # None when no ANTHROPIC_API_KEY is set
        self._reminders = reminders
        self._clarifications = clarifications
        self._clock = clock
        self._max_input_chars = max_input_chars

    # --- a typed message ------------------------------------------------------

    async def on_text(self, event: IncomingEvent, user: UserProfile, channel: Channel) -> None:
        lang = user.language
        text = event.text.strip()
        if self._parser is None:
            await channel.send_message(event.chat_id, t("fallback.not_yet", lang))
            return
        if len(text) > self._max_input_chars:
            # Too long to send to the AI (cost control). We say so instead of cutting it.
            await channel.send_message(
                event.chat_id, t("nl.too_long", lang, max=self._max_input_chars)
            )
            return

        now = self._clock.now()
        try:
            now_local = now.astimezone(ZoneInfo(user.timezone))
            parsed = await self._parser.parse(text, now_local, user.timezone)
        except ParserError as error:
            log.warning("parse_failed", reason=str(error))
            await channel.send_message(event.chat_id, t("ai.unavailable", lang))
            return

        open_question = await self._clarifications.get(user.id, now)
        titled = [item for item in parsed.items if item.title]
        if open_question is not None and not titled:
            # No new task in the message, so it's the answer to our question.
            await self._answer_typed(event, user, channel, open_question, parsed, text)
            return

        if parsed.intent == "question":
            await channel.send_message(event.chat_id, t("nl.question_not_yet", lang))
            return
        if not titled:
            await channel.send_message(event.chat_id, t("nl.not_understood", lang))
            return
        await self._handle_new_items(event, user, channel, titled, text, open_question)

    async def _handle_new_items(
        self,
        event: IncomingEvent,
        user: UserProfile,
        channel: Channel,
        items: list[ParsedItem],
        text: str,
        open_question: Clarification | None,
    ) -> None:
        # dateparser's second opinion only makes sense when the message has one date.
        check_text = text if len(items) == 1 else None
        waiting = []
        for item in items:
            kind = _kind_for(item.when, ReminderKind(item.kind))
            plan = await self._plan(item.when, item.confidence, user, check_text)
            if isinstance(plan, Resolved):
                await self._save(event, user, channel, item.title, kind, plan, text)
            else:
                waiting.append(_pending(item.title, kind, plan, text))

        if not waiting:
            return
        # Keep any older unanswered items first; we never drop a reminder silently.
        queue = (open_question.queue if open_question else []) + waiting
        await self._ask_next(event, user, channel, queue)

    async def _answer_typed(
        self,
        event: IncomingEvent,
        user: UserProfile,
        channel: Channel,
        question: Clarification,
        parsed: ParsedMessage,
        text: str,
    ) -> None:
        item, rest = question.queue[0], question.queue[1:]
        if parsed.intent != "reminder" or not parsed.items:
            await channel.send_message(event.chat_id, t("clarify.didnt_get", user.language))
            await self._ask(event, user, channel, question)
            return

        answer = parsed.items[0]
        kind = _kind_for(answer.when, item.kind)
        plan = await self._plan(answer.when, answer.confidence, user, text)
        if isinstance(plan, Resolved):
            await self._save(
                event,
                user,
                channel,
                item.title,
                kind,
                plan,
                item.source_text,
                item.edit_reminder_id,
            )
            await self._ask_next(event, user, channel, rest)
        else:
            # Still not clear: ask again about the same task, with the new options.
            again = _pending(item.title, kind, plan, item.source_text, item.edit_reminder_id)
            await self._ask_next(event, user, channel, [again, *rest])

    # --- a button press -------------------------------------------------------

    async def on_button(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, data: str
    ) -> None:
        """`data` is what follows "cl:", e.g. "aB3dE5fG:0" or "aB3dE5fG:x"."""
        token, _, choice = data.partition(":")
        question = await self._clarifications.get(user.id, self._clock.now())
        if question is None or question.token != token:
            # An old button: the question was answered, replaced or has expired.
            await channel.send_message(event.chat_id, t("clarify.expired", user.language))
            return

        item, rest = question.queue[0], question.queue[1:]
        if choice == CANCEL:
            await channel.send_message(
                event.chat_id, t("clarify.cancelled", user.language, title=item.title)
            )
        elif choice.isdigit() and int(choice) < len(item.choices):
            chosen = item.choices[int(choice)]
            if chosen.due_at_utc <= self._clock.now():
                # They waited so long that this choice is now in the past: ask for a new time.
                again = _pending(
                    item.title,
                    item.kind,
                    Ask("clarify.past"),
                    item.source_text,
                    item.edit_reminder_id,
                )
                await self._ask_next(event, user, channel, [again, *rest])
                return
            await self._save(
                event,
                user,
                channel,
                item.title,
                item.kind,
                chosen,
                item.source_text,
                item.edit_reminder_id,
            )
        else:
            log.warning("bad_clarify_button", data_len=len(data))
            return
        await self._ask_next(event, user, channel, rest)

    # --- /edit ----------------------------------------------------------------

    async def ask_new_time(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, info: ReminderInfo
    ) -> None:
        """Ask "When is X due now?". The answer is handled like any other clarification."""
        if self._parser is None:
            await channel.send_message(event.chat_id, t("fallback.not_yet", user.language))
            return
        item = PendingReminder(
            title=info.title, kind=info.kind, question_key="edit.ask", edit_reminder_id=info.id
        )
        # The user just asked for this, so it goes before any older open questions.
        open_question = await self._clarifications.get(user.id, self._clock.now())
        older = open_question.queue if open_question else []
        await self._ask_next(event, user, channel, [item, *older])

    # --- helpers --------------------------------------------------------------

    async def _plan(
        self, spec: WhenSpec, confidence: float, user: UserProfile, check_text: str | None
    ) -> Resolved | Ask:
        """Work out the moment, and decide whether we must ask the user first."""
        now = self._clock.now()
        result = resolve(spec, user.timezone, now)
        if not isinstance(result, Resolved):
            return result

        unsure = confidence < CONFIDENCE_THRESHOLD
        if not unsure and check_text is not None and worth_checking(spec):
            # dateparser can be slow, so it runs in a thread to keep the bot responsive.
            agree = await asyncio.to_thread(
                dates_agree, check_text, result.due_at_utc, user.timezone, now
            )
            if not agree:
                log.info("crosscheck_disagrees")
                unsure = True
        if unsure:
            due = format_datetime(result.due_at_utc, user.timezone)
            return Ask("clarify.confirm", {"due": due}, [result])
        return result

    async def _save(
        self,
        event: IncomingEvent,
        user: UserProfile,
        channel: Channel,
        title: str,
        kind: ReminderKind,
        when: Resolved,
        source_text: str | None,
        edit_id: int | None = None,
    ) -> None:
        """Save a new reminder, or (with edit_id) move an existing one to the new time."""
        try:
            if edit_id is None:
                saved = await self._reminders.create(
                    user.id, title, when.due_at_utc, kind, source_text=source_text
                )
            else:
                saved = await self._reminders.edit_due(user.id, edit_id, when.due_at_utc)
        except ValueError:  # the moment passed while we were working
            await channel.send_message(event.chat_id, t("nl.passed", user.language, title=title))
            return
        if saved is None:  # edited a reminder that was done or deleted meanwhile
            await channel.send_message(event.chat_id, t("reminder.gone", user.language))
            return
        log.info("reminder_saved", reminder_id=saved.id, edited=edit_id is not None)
        now = self._clock.now()
        await send_confirmation(channel, event.chat_id, saved, user, now, when.time_defaulted)

    async def _ask_next(
        self,
        event: IncomingEvent,
        user: UserProfile,
        channel: Channel,
        queue: list[PendingReminder],
    ) -> None:
        """Store what's still waiting and ask about the first one (or clear if none)."""
        expires = self._clock.now() + CLARIFY_TTL
        question = await self._clarifications.replace(user.id, queue, expires)
        if question is not None:
            await self._ask(event, user, channel, question)

    async def _ask(
        self, event: IncomingEvent, user: UserProfile, channel: Channel, question: Clarification
    ) -> None:
        lang = user.language
        item = question.queue[0]
        text = t(item.question_key, lang, title=item.title, **item.question_args)
        prefix = f"{CLARIFY_PREFIX}{question.token}:"
        rows = [
            [Button(describe_choice(choice, user.timezone), f"{prefix}{number}")]
            for number, choice in enumerate(item.choices)
        ]
        rows.append([Button(t("button.cancel", lang), f"{prefix}{CANCEL}")])
        await channel.send_buttons(event.chat_id, text, rows)


def _kind_for(spec: WhenSpec, suggested: ReminderKind) -> ReminderKind:
    # "in 2 hours" is always a one-off alert at that moment (CLAUDE.md rule 4).
    return ReminderKind.AT_TIME if spec.relative_minutes is not None else suggested


def _pending(
    title: str,
    kind: ReminderKind,
    ask: Ask,
    source_text: str | None,
    edit_reminder_id: int | None = None,
) -> PendingReminder:
    return PendingReminder(
        title=title,
        kind=kind,
        question_key=ask.question_key,
        question_args=ask.args,
        choices=ask.choices,
        source_text=source_text,
        edit_reminder_id=edit_reminder_id,
    )
