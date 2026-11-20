"""Small domain types shared by core/ and db/.

They are StrEnums, so each value is also a plain string ("pending", "sent", ...).
That is exactly what we store in the database.
"""

from enum import StrEnum


class ReminderKind(StrEnum):
    DEADLINE = "deadline"  # alerts 1 day, 3 h and 30 min before (CLAUDE.md rule 4)
    AT_TIME = "at_time"  # one alert at that exact time ("remind me in 2 hours to ...")


class ReminderStatus(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    DELETED = "deleted"


class AlertStatus(StrEnum):
    PENDING = "pending"  # waiting for its send time
    SENDING = "sending"  # claimed by the scheduler, send in progress
    SENT = "sent"
    FAILED = "failed"  # gave up after too many attempts
    CANCELLED = "cancelled"  # reminder was done/deleted before the alert went out


class PendingKind(StrEnum):
    """What the bot is waiting for the user to answer (stored in `pending_actions`)."""

    AWAIT_TIMEZONE = "await_timezone"  # user pressed "Other" and must type a timezone
    CLARIFY_REMINDER = "clarify_reminder"  # we asked "which day do you mean?" (core/clarify.py)
