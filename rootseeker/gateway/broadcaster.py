from __future__ import annotations

from dataclasses import dataclass

from rootseeker.gateway.connection import GatewayConnection
from rootseeker.gateway.event_sink import InMemoryEventSink
from rootseeker.gateway.protocol import GatewayEventFrame
from rootseeker.gateway.subscriptions import SubscriptionRegistry

__all__ = ["BroadcastResult", "GatewayBroadcaster"]


@dataclass
class BroadcastResult:
    topic: str
    delivered_count: int
    dropped_clients: list[str]


class GatewayBroadcaster:
    def __init__(
        self,
        *,
        connections: dict[str, GatewayConnection],
        subscriptions: SubscriptionRegistry,
        sink: InMemoryEventSink,
        max_inbox_size: int = 200,
    ) -> None:
        self._connections = connections
        self._subscriptions = subscriptions
        self._sink = sink
        self._max_inbox_size = max_inbox_size

    def broadcast(self, event: GatewayEventFrame) -> BroadcastResult:
        self._sink.publish(event.model_dump(mode="json"))
        delivered = 0
        dropped: list[str] = []
        for client_id in self._subscriptions.resolve_clients(event.topic):
            connection = self._connections.get(client_id)
            if connection is None:
                continue
            if len(connection.inbox) >= self._max_inbox_size:
                dropped.append(client_id)
                continue
            connection.inbox.append(event)
            delivered += 1
        return BroadcastResult(
            topic=event.topic, delivered_count=delivered, dropped_clients=dropped
        )
