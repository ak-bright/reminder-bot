"""Reminders waiting for an answer from the user ("Which Friday do you mean?").

When a message has unclear items, they wait in a queue. The bot asks about the
first one; when it's answered (by a button or a typed reply) the next one is asked.
The queue is stored in the database (`pending_actions`), so it survives a restart.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from reminderbot.core.models import ReminderKind
from reminderbot.core.when import Resolved


@dataclass
class PendingReminder:
    title: str
    kind: ReminderKind
    question_key: str  # strings.py key of the question to ask
    question_args: dict[str, str] = field(default_factory=dict)
    choices: list[Resolved] = field(default_factory=list)  # one button per choice
    source_text: str | None = None
    edit_reminder_id: int | None = None  # set when this is /edit: move that reminder


@dataclass
class Clarification:
    # A random code put on the buttons, so an old button can't answer a newer question.
    # (Not the row id: SQLite reuses the id of a deleted row.)
    token: str
    queue: list[PendingReminder]


class ClarificationStore(Protocol):
    async def get(self, user_id: int, now: datetime) -> Clarification | None:
        """The user's open clarification, if any (and not expired)."""
        ...

    async def replace(
        self, user_id: int, queue: list[PendingReminder], expires_at: datetime
    ) -> Clarification | None:
        """Drop the old clarification and store this queue. An empty queue just clears it."""
        ...
