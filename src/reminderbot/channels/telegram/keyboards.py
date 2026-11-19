"""Convert our channel-agnostic Buttons into a Telegram inline keyboard."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from reminderbot.channels.base import Button


def to_inline_keyboard(buttons: list[list[Button]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.label, callback_data=b.data) for b in row] for row in buttons]
    )
