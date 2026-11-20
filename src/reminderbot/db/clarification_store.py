"""SqlClarificationStore: keeps core's clarification queue in `pending_actions`.

The queue is saved as JSON in the row's `payload`. Datetimes become ISO strings
(always UTC) and come back as timezone-aware datetimes.
"""

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reminderbot.core.clarify import Clarification, PendingReminder
from reminderbot.core.models import PendingKind, ReminderKind
from reminderbot.core.when import Resolved
from reminderbot.db.repositories import PendingActionRepo

KIND = PendingKind.CLARIFY_REMINDER


class SqlClarificationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, user_id: int, now: datetime) -> Clarification | None:
        async with self._session_factory() as session:
            row = await PendingActionRepo(session).find(user_id, KIND, now)
            if row is None:
                return None
            queue = [_from_json(item) for item in row.payload.get("queue", [])]
            return Clarification(token=row.payload["token"], queue=queue) if queue else None

    async def replace(
        self, user_id: int, queue: list[PendingReminder], expires_at: datetime
    ) -> Clarification | None:
        async with self._session_factory() as session:
            repo = PendingActionRepo(session)
            await repo.delete_kind(user_id, KIND)
            result = None
            if queue:
                token = secrets.token_urlsafe(6)  # 8 characters, keeps buttons short
                payload = {"token": token, "queue": [_to_json(item) for item in queue]}
                await repo.add(user_id, KIND, payload, expires_at)
                result = Clarification(token=token, queue=queue)
            await session.commit()
            return result


def _to_json(item: PendingReminder) -> dict[str, Any]:
    return {
        "title": item.title,
        "kind": str(item.kind),
        "question_key": item.question_key,
        "question_args": item.question_args,
        "choices": [
            {"due": c.due_at_utc.isoformat(), "defaulted": c.time_defaulted} for c in item.choices
        ],
        "source_text": item.source_text,
        "edit_reminder_id": item.edit_reminder_id,
    }


def _from_json(data: dict[str, Any]) -> PendingReminder:
    return PendingReminder(
        title=data["title"],
        kind=ReminderKind(data["kind"]),
        question_key=data["question_key"],
        question_args=data.get("question_args", {}),
        choices=[
            Resolved(datetime.fromisoformat(c["due"]), c["defaulted"]) for c in data["choices"]
        ],
        source_text=data.get("source_text"),
        edit_reminder_id=data.get("edit_reminder_id"),
    )
