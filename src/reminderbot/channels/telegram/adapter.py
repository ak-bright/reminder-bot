"""TelegramChannel: our Channel interface implemented with the Telegram Bot API."""

from telegram import Bot, Update

from reminderbot.channels.base import Button, Channel, IncomingEvent
from reminderbot.channels.telegram.keyboards import to_inline_keyboard

CHANNEL_NAME = "telegram"


class TelegramChannel(Channel):
    name = CHANNEL_NAME

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: str, text: str) -> None:
        # No parse_mode: we send plain text, so user content never breaks formatting.
        await self._bot.send_message(chat_id=int(chat_id), text=text)

    async def send_buttons(self, chat_id: str, text: str, buttons: list[list[Button]]) -> None:
        await self._bot.send_message(
            chat_id=int(chat_id), text=text, reply_markup=to_inline_keyboard(buttons)
        )


def event_from_update(update: Update) -> IncomingEvent | None:
    """Translate a Telegram Update into our IncomingEvent (None if we don't handle it)."""
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None:
        return None

    if update.callback_query is not None:
        return IncomingEvent(
            channel=CHANNEL_NAME,
            channel_user_id=str(user.id),
            chat_id=str(chat.id),
            button_data=update.callback_query.data or "",
            display_name=user.first_name,
        )

    message = update.effective_message
    if message is not None and message.text is not None:
        return IncomingEvent(
            channel=CHANNEL_NAME,
            channel_user_id=str(user.id),
            chat_id=str(chat.id),
            text=message.text,
            display_name=user.first_name,
        )
    return None
