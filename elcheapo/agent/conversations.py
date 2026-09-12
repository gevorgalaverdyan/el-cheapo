"""Deciding which conversation a message belongs to.

A chat's context should carry across a correction -- "make it 52" needs the
merchant from thirty seconds ago -- without carrying across the gap between
lunch and the taxi home. So a conversation ends after a stretch of silence,
and the user can end one on demand.

Kept free of ADK so the policy is testable against a fake clock.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable

DEFAULT_IDLE_TIMEOUT = timedelta(minutes=15)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Conversations:
    """Maps a chat to its current session id."""

    def __init__(
        self,
        *,
        idle_timeout: timedelta = DEFAULT_IDLE_TIMEOUT,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self._idle_timeout = idle_timeout
        self._clock = clock
        # chat id -> (session number, when it was last used)
        self._state: dict[int, tuple[int, datetime]] = {}

    def session_for(self, chat_id: int) -> str:
        """The session this chat's next message belongs to.

        Reading is also touching: the idle window is time since the last
        message, not time since the conversation began, so a long
        back-and-forth is never cut off midway.
        """
        now = self._clock()
        number, last_used = self._state.get(chat_id, (0, now))

        if now - last_used > self._idle_timeout:
            number += 1

        self._state[chat_id] = (number, now)
        return f"chat-{chat_id}-{number}"

    def reset(self, chat_id: int) -> None:
        """Abandon this chat's current conversation.

        The next message opens a fresh one. Safe on a chat that has never
        spoken, and safe to call repeatedly.
        """
        number, _ = self._state.get(chat_id, (0, self._clock()))
        self._state[chat_id] = (number + 1, self._clock())
