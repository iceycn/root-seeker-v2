from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

__all__ = ["EventBus", "EventHandler"]

EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(topic, []):
            handler(dict(payload))
