"""The Telegram adapter's translation from Telegram objects to our IncomingEvent."""

from datetime import UTC, datetime

from telegram import CallbackQuery, Chat, Message, Update, User

from reminderbot.channels.base import Button
from reminderbot.channels.telegram.adapter import event_from_update
from reminderbot.channels.telegram.keyboards import to_inline_keyboard

USER = User(id=111, first_name="Kofi", is_bot=False)
CHAT = Chat(id=111, type=Chat.PRIVATE)


def test_text_message_becomes_event():
    message = Message(
        message_id=1, date=datetime.now(UTC), chat=CHAT, from_user=USER, text="/start"
    )
    event = event_from_update(Update(update_id=1, message=message))
    assert event is not None
    assert event.channel == "telegram"
    assert event.channel_user_id == "111"
    assert event.chat_id == "111"
    assert event.text == "/start"
    assert event.button_data is None
    assert event.display_name == "Kofi"


def test_button_press_becomes_event():
    message = Message(message_id=2, date=datetime.now(UTC), chat=CHAT, text="pick one")
    query = CallbackQuery(
        id="q1", from_user=USER, chat_instance="c", data="tz:Africa/Accra", message=message
    )
    event = event_from_update(Update(update_id=2, callback_query=query))
    assert event is not None
    assert event.button_data == "tz:Africa/Accra"
    assert event.chat_id == "111"


def test_keyboard_layout():
    markup = to_inline_keyboard([[Button("A", "a"), Button("B", "b")], [Button("C", "c")]])
    rows = markup.inline_keyboard
    assert [[b.callback_data for b in row] for row in rows] == [["a", "b"], ["c"]]
