"""Small in-memory event log rendered in the sidebar panel."""

from __future__ import annotations

from collections import deque
from typing import Any

from homeassistant.util import dt as dt_util

from .const import LOG_LIMIT


class EventLog:
    """Ring buffer of recent integration events."""

    def __init__(self, limit: int = LOG_LIMIT) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=limit)

    def add(
        self,
        level: str,
        event: str,
        message: str,
        user: str | None = None,
    ) -> None:
        self._entries.appendleft(
            {
                "ts": dt_util.now().isoformat(),
                "level": level,
                "event": event,
                "message": str(message)[:500],
                "user": user,
            }
        )

    def info(self, event: str, message: str, user: str | None = None) -> None:
        self.add("info", event, message, user)

    def warning(self, event: str, message: str, user: str | None = None) -> None:
        self.add("warning", event, message, user)

    def error(self, event: str, message: str, user: str | None = None) -> None:
        self.add("error", event, message, user)

    def as_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._entries)[:limit]
