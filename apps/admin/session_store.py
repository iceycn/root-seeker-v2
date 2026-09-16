from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

__all__ = ["SESSION_COOKIE_NAME", "SESSION_TTL_SECONDS", "SessionRecord", "SessionStore"]

SESSION_COOKIE_NAME = "rootseeker_admin_session"
SESSION_TTL_SECONDS = 12 * 3600


@dataclass
class SessionRecord:
    user_id: str
    username: str
    expires_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, user_id: str, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        record = SessionRecord(
            user_id=user_id,
            username=username,
            expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_TTL_SECONDS),
        )
        with self._lock:
            self._sessions[session_id] = record
        return session_id

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            if datetime.now(UTC) >= record.expires_at:
                self._sessions.pop(session_id, None)
                return None
            return record

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def delete_by_user_id(self, user_id: str) -> None:
        with self._lock:
            stale = [key for key, rec in self._sessions.items() if rec.user_id == user_id]
            for key in stale:
                self._sessions.pop(key, None)
