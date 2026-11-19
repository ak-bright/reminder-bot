"""SqlUserStore: the database version of core's UserStore.

UserService (core/users.py) works with plain UserProfile objects and never sees
the database. This class turns UserProfile into `users` rows and back.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reminderbot.clock import Clock
from reminderbot.core.models import PendingKind
from reminderbot.core.users import UserProfile
from reminderbot.db.models import User
from reminderbot.db.repositories import PendingActionRepo, UserRepo


class SqlUserStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def get(self, channel: str, channel_user_id: str) -> UserProfile | None:
        async with self._session_factory() as session:
            row = await UserRepo(session).get_by_identity(channel, channel_user_id)
            if row is None:
                return None
            waiting = await PendingActionRepo(session).find(
                row.id, PendingKind.AWAIT_TIMEZONE, self._clock.now()
            )
            return UserProfile(
                id=row.id,
                channel=row.channel,
                channel_user_id=row.channel_user_id,
                name=row.name,
                timezone=row.timezone,
                language=row.language,
                awaiting_timezone=waiting is not None,
                is_new=not row.onboarded,
            )

    async def save(self, user: UserProfile) -> None:
        async with self._session_factory() as session:
            users = UserRepo(session)
            row = await users.get_by_identity(user.channel, user.channel_user_id)
            is_insert = row is None
            if is_insert:
                row = User(channel=user.channel, channel_user_id=user.channel_user_id)
            row.name = user.name
            row.timezone = user.timezone
            row.language = user.language
            row.onboarded = not user.is_new
            if is_insert:
                await users.add(row)  # after the fields are set: timezone is NOT NULL

            # "Waiting for a typed timezone" is stored as a pending action.
            pending = PendingActionRepo(session)
            await pending.delete_kind(row.id, PendingKind.AWAIT_TIMEZONE)
            if user.awaiting_timezone:
                await pending.add(row.id, PendingKind.AWAIT_TIMEZONE)

            await session.commit()
            user.id = row.id
