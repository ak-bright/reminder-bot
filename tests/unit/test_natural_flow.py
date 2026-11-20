"""The conversation around plain-language reminders: questions, buttons, typed answers.

The AI is the FakeParser from conftest.py. "Now" is Wed 18 Nov 2026, 14:30 UTC.
"""

from datetime import UTC, datetime

from reminderbot.ai.parser import ParserError
from reminderbot.ai.schemas import ParsedItem, ParsedMessage
from reminderbot.channels.base import IncomingEvent
from reminderbot.channels.natural import NaturalLanguage
from reminderbot.channels.router import Router
from reminderbot.core.models import AlertStatus
from reminderbot.core.reminders import ReminderService
from reminderbot.db.clarification_store import SqlClarificationStore
from reminderbot.db.reminder_store import SqlReminderStore
from reminderbot.db.repositories import AlertRepo, ReminderRepo, UserRepo
from reminderbot.strings import t
from tests.ai.test_parsing_cases import when


def msg(text: str) -> IncomingEvent:
    return IncomingEvent(channel="fake", channel_user_id="42", chat_id="42", text=text)


def press(data: str) -> IncomingEvent:
    return IncomingEvent(channel="fake", channel_user_id="42", chat_id="42", button_data=data)


def reply(*items: ParsedItem) -> ParsedMessage:
    return ParsedMessage(intent="reminder", items=list(items))


def task(title: str, confidence: float = 0.95, **when_fields) -> ParsedItem:
    return ParsedItem(title=title, kind="deadline", when=when(**when_fields), confidence=confidence)


def buttons(sent: dict) -> list[tuple[str, str]]:
    return [(b.label, b.data) for row in sent["buttons"] for b in row]


async def saved_reminders(session_factory):
    async with session_factory() as session:
        user = await UserRepo(session).get_by_identity("fake", "42")
        return list(await ReminderRepo(session).list_active(user.id))


# --- answering with a button ----------------------------------------------------


async def test_choosing_a_button_saves_the_reminder(router, channel, parser, session_factory):
    parser.answers.append(reply(task("Essay", weekday="friday", weekday_modifier="next")))
    await router.handle(msg("next Friday essay"), channel)
    choices = buttons(channel.last)
    assert [label for label, _ in choices] == [
        "Fri 20 Nov, 8:00 AM",
        "Fri 27 Nov, 8:00 AM",
        t("button.cancel"),
    ]
    assert all(len(data.encode()) <= 64 for _, data in choices)  # Telegram's limit

    await router.handle(press(choices[1][1]), channel)  # "Fri 27 Nov"
    assert channel.last["text"].startswith("Got it. Essay, due Fri 27 Nov, 8:00 AM.")
    [reminder] = await saved_reminders(session_factory)
    assert reminder.due_at_utc == datetime(2026, 11, 27, 8, 0, tzinfo=UTC)

    # The question is answered, so pressing an old button again does nothing harmful.
    await router.handle(press(choices[0][1]), channel)
    assert channel.last["text"] == t("clarify.expired")
    assert len(await saved_reminders(session_factory)) == 1


async def test_cancel_saves_nothing(router, channel, parser, session_factory):
    parser.answers.append(reply(task("Project", day_word="next_week")))
    await router.handle(msg("project due next week"), channel)
    cancel = buttons(channel.last)[-1][1]
    await router.handle(press(cancel), channel)
    assert channel.last["text"] == t("clarify.cancelled", title="Project")
    assert await saved_reminders(session_factory) == []


async def test_bad_button_data_is_ignored(router, channel, parser, session_factory):
    parser.answers.append(reply(task("Project", day_word="next_week")))
    await router.handle(msg("project due next week"), channel)
    token = buttons(channel.last)[0][1].split(":")[1]
    count = len(channel.sent)
    await router.handle(press(f"cl:{token}:99"), channel)
    await router.handle(press(f"cl:{token}:abc"), channel)
    assert len(channel.sent) == count  # nothing sent, nothing saved
    assert await saved_reminders(session_factory) == []


async def test_question_expires_after_an_hour(router, channel, parser, clock):
    parser.answers.append(reply(task("Project", day_word="next_week")))
    await router.handle(msg("project due next week"), channel)
    monday = buttons(channel.last)[0][1]
    clock.advance(hours=2)
    await router.handle(press(monday), channel)
    assert channel.last["text"] == t("clarify.expired")


async def test_a_choice_that_became_past_asks_again(router, channel, parser, clock):
    parser.answers.append(reply(task("Quiz", weekday="wednesday", time="15:00")))
    await router.handle(msg("Wednesday quiz 3pm"), channel)  # today 3 PM, or next week?
    today_button = buttons(channel.last)[0][1]
    clock.advance(minutes=45)  # now 15:15: "today 3 PM" has passed
    await router.handle(press(today_button), channel)
    assert channel.last["text"] == t("clarify.past", title="Quiz")


# --- answering by typing ---------------------------------------------------------


async def test_typed_answer_to_when_question(router, channel, parser, session_factory):
    parser.answers.append(reply(task("DS assignment")))
    await router.handle(msg("DS assignment"), channel)
    assert channel.last["text"] == t("clarify.when", title="DS assignment")

    # The answer has no title of its own, so it belongs to the open question.
    parser.answers.append(reply(task("", weekday="friday", time="17:00")))
    await router.handle(msg("Friday 5pm"), channel)
    assert channel.last["text"].startswith("Got it. DS assignment, due Fri 20 Nov, 5:00 PM.")
    [reminder] = await saved_reminders(session_factory)
    assert reminder.title == "DS assignment"
    assert reminder.source_text == "DS assignment"  # the original message is kept


async def test_typed_answer_without_a_time_asks_again(router, channel, parser):
    parser.answers.append(reply(task("DS assignment")))
    await router.handle(msg("DS assignment"), channel)
    parser.answers.append(ParsedMessage(intent="other", items=[]))
    await router.handle(msg("hmm not sure"), channel)
    assert channel.sent[-2]["text"] == t("clarify.didnt_get")
    assert channel.last["text"] == t("clarify.when", title="DS assignment")


async def test_typed_answer_that_is_still_unclear_asks_a_new_question(router, channel, parser):
    parser.answers.append(reply(task("DS assignment")))
    await router.handle(msg("DS assignment"), channel)
    parser.answers.append(reply(task("", day_word="next_week")))
    await router.handle(msg("next week"), channel)
    assert channel.last["text"] == t("clarify.which_day", title="DS assignment")
    assert len(buttons(channel.last)) == 6  # Mon-Fri + Cancel


# --- several unclear items ----------------------------------------------------------


async def test_unclear_items_are_asked_one_at_a_time(router, channel, parser, session_factory):
    parser.answers.append(
        reply(
            task("Essay", day_word="next_week"),
            task("Lab", weekday="friday", weekday_modifier="next"),
        )
    )
    await router.handle(msg("essay next week, lab next friday"), channel)
    assert channel.last["text"] == t("clarify.which_day", title="Essay")
    await router.handle(press(buttons(channel.last)[0][1]), channel)  # Monday

    assert channel.sent[-2]["text"].startswith("Got it. Essay, due Mon 23 Nov")
    assert channel.last["text"] == t("clarify.next_weekday", title="Lab", weekday="Friday")
    await router.handle(press(buttons(channel.last)[1][1]), channel)  # Fri 27 Nov
    assert channel.last["text"].startswith("Got it. Lab, due Fri 27 Nov")
    assert len(await saved_reminders(session_factory)) == 2


async def test_new_task_while_a_question_is_open_is_not_lost(router, channel, parser):
    parser.answers.append(reply(task("Essay", day_word="next_week")))
    await router.handle(msg("essay next week"), channel)
    old_button = buttons(channel.last)[0][1]

    # A new task with a title is a new reminder, not the answer.
    parser.answers.append(reply(task("Quiz", weekday="friday", weekday_modifier="next")))
    await router.handle(msg("quiz next friday"), channel)
    # The essay is still waiting, so we ask about it first (with fresh buttons).
    assert channel.last["text"] == t("clarify.which_day", title="Essay")
    assert buttons(channel.last)[0][1] != old_button

    await router.handle(press(old_button), channel)  # buttons from the old message
    assert channel.last["text"] == t("clarify.expired")


async def test_question_survives_a_restart(channel, parser, users, session_factory, clock):
    def new_router() -> Router:
        reminders = ReminderService(SqlReminderStore(session_factory), clock)
        store = SqlClarificationStore(session_factory)
        natural = NaturalLanguage(parser, reminders, store, clock, max_input_chars=2000)
        return Router(users, reminders, natural, clock)

    parser.answers.append(reply(task("Project", day_word="next_week")))
    await new_router().handle(msg("project due next week"), channel)
    tuesday = buttons(channel.last)[1][1]

    await new_router().handle(press(tuesday), channel)  # a brand-new bot process
    assert channel.last["text"].startswith("Got it. Project, due Tue 24 Nov, 8:00 AM.")


# --- limits and failures ---------------------------------------------------------------


async def test_too_long_message_is_not_sent_to_the_ai(router, channel, parser):
    await router.handle(msg("x" * 2001), channel)
    assert parser.calls == []
    assert channel.last["text"] == t("nl.too_long", max=2000)


async def test_ai_failure_gives_a_friendly_message(router, channel, parser):
    parser.answers.append(ParserError("API error 529"))
    await router.handle(msg("essay due friday"), channel)
    assert channel.last["text"] == t("ai.unavailable")


async def test_without_an_api_key_plain_text_points_to_remind(
    users, reminders, session_factory, clock, channel
):
    natural = NaturalLanguage(None, reminders, SqlClarificationStore(session_factory), clock, 2000)
    router = Router(users, reminders, natural, clock)
    await router.handle(msg("essay due friday"), channel)
    assert channel.last["text"] == t("fallback.not_yet")


async def test_saved_reminder_gets_its_alerts(router, channel, parser, session_factory):
    parser.answers.append(reply(task("DS assignment", weekday="friday", time="17:00")))
    await router.handle(msg("DS assignment due Friday 5pm"), channel)
    [reminder] = await saved_reminders(session_factory)
    async with session_factory() as session:
        alerts = await AlertRepo(session).list_for_reminder(reminder.id)
    assert [a.send_at_utc for a in alerts] == [
        datetime(2026, 11, 19, 17, 0, tzinfo=UTC),  # 1 day before
        datetime(2026, 11, 20, 14, 0, tzinfo=UTC),  # 3 hours before
        datetime(2026, 11, 20, 16, 30, tzinfo=UTC),  # 30 minutes before
    ]
    assert all(a.status == AlertStatus.PENDING for a in alerts)


# --- a user in a non-UTC timezone with daylight saving ---------------------------------------


async def test_new_york_user_times_are_local(router, channel, parser, users, session_factory):
    user = await users.get_or_create("fake", "42", None)
    await users.set_timezone(user, "America/New_York")

    # New York is UTC-5 in November (after DST ended on 1 Nov).
    parser.answers.append(reply(task("Essay", weekday="friday", time="17:00")))
    await router.handle(msg("essay due Friday 5pm"), channel)
    assert "Fri 20 Nov, 5:00 PM" in channel.last["text"]

    # ...and UTC-4 in March (DST starts 14 March 2027).
    parser.answers.append(reply(task("Exam", month=3, day=20, time="17:00")))
    await router.handle(msg("exam 20 March 5pm"), channel)
    assert "Sat 20 Mar, 5:00 PM" in channel.last["text"]

    essay, exam = await saved_reminders(session_factory)
    assert essay.due_at_utc == datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
    assert exam.due_at_utc == datetime(2027, 3, 20, 21, 0, tzinfo=UTC)
    # The parser was told the user's local time and zone.
    assert parser.calls[-1] == "exam 20 March 5pm"
