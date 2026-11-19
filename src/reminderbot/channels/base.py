"""The channel-agnostic interface.

Each chat app (Telegram, later WhatsApp) has an adapter that:
  1. turns the app's incoming update into an IncomingEvent, and
  2. implements Channel so the rest of the bot can send messages and buttons.
The bot logic (router.py) and the scheduler only ever see these types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Button:
    label: str  # what the user sees
    data: str  # what comes back when pressed (keep it short: Telegram allows 64 bytes)


@dataclass(frozen=True)
class IncomingEvent:
    channel: str  # "telegram", "whatsapp", ...
    channel_user_id: str
    chat_id: str  # where to send replies
    text: str = ""  # message text ("" for button presses)
    button_data: str | None = None  # set when the user pressed a button
    display_name: str | None = None


class Channel(ABC):
    name: str

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> None: ...

    @abstractmethod
    async def send_buttons(self, chat_id: str, text: str, buttons: list[list[Button]]) -> None:
        """Send text with buttons. `buttons` is a list of rows, each row a list of buttons."""


def parse_command(text: str) -> tuple[str | None, str]:
    """Split '/start hello' into ('start', 'hello'). Non-commands give (None, text).

    Also handles Telegram's '/start@MyBot' form.
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, stripped
    head, _, rest = stripped.partition(" ")
    command = head[1:].split("@", 1)[0].lower()
    return (command or None), rest.strip()
