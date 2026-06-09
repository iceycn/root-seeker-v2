from __future__ import annotations

from typing import Any

__all__ = ["InMemoryEventSink"]


class InMemoryEventSink:
    """In-memory control-plane event buffer for dev/runtime inspection."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> None:
        self._events.append(dict(event))

    def list_events(self, *, limit: int = 200) -> list[dict[str, Any]]:
        if limit < 0:
            return list(self._events)
        return list(self._events[-limit:])
