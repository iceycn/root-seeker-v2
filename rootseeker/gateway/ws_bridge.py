"""Bridge WebSocket transport subscriptions with GatewayServer registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from rootseeker.gateway.connection import GatewayConnection
from rootseeker.gateway.protocol import GatewayEventFrame
from rootseeker.gateway.server import GatewayServer
from rootseeker.gateway.websocket_transport import WebSocketTransport

__all__ = ["GatewayWsBridge"]


class GatewayWsBridge:
    """Keep WS frame subscriptions and Gateway subscription registry in sync."""

    def __init__(
        self,
        gateway_server: GatewayServer,
        ws_transport: WebSocketTransport,
    ) -> None:
        self._gateway_server = gateway_server
        self._ws_transport = ws_transport
        self._pending_broadcasts: list[tuple[str, GatewayEventFrame]] = []
        self._wire_transport_handlers()

    def ensure_client(self, connection_id: str) -> str:
        client_id = self._client_id_for_connection(connection_id)
        if client_id not in self._gateway_server.connections:
            self._gateway_server.connections[client_id] = GatewayConnection(
                client_id=client_id
            )
        state = self._ws_transport._connections.get(connection_id)
        if state is not None and state.client_id is None:
            state.client_id = client_id
        return client_id

    def subscribe(self, connection_id: str, topic: str) -> str:
        client_id = self.ensure_client(connection_id)
        self._gateway_server.subscriptions.subscribe(client_id, topic)
        connection = self._gateway_server.connections[client_id]
        connection.subscriptions.add(topic)
        state = self._ws_transport._connections.get(connection_id)
        if state is not None:
            state.subscriptions.add(topic)
        return client_id

    def unsubscribe(self, connection_id: str, topic: str) -> str:
        client_id = self._client_id_for_connection(connection_id)
        self._gateway_server.subscriptions.unsubscribe(client_id, topic)
        connection = self._gateway_server.connections.get(client_id)
        if connection is not None:
            connection.subscriptions.discard(topic)
        state = self._ws_transport._connections.get(connection_id)
        if state is not None:
            state.subscriptions.discard(topic)
        return client_id

    def disconnect(self, connection_id: str) -> None:
        client_id = self._client_id_for_connection(connection_id)
        self._gateway_server.subscriptions.remove_client(client_id)
        self._gateway_server.connections.pop(client_id, None)

    def publish(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._gateway_server.publish(topic, payload)
        self.queue_broadcast(topic, payload)
        return result

    def queue_broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        self._pending_broadcasts.append(
            (topic, GatewayEventFrame(topic=topic, payload=payload))
        )

    async def flush_broadcasts(self) -> int:
        delivered = 0
        pending = list(self._pending_broadcasts)
        self._pending_broadcasts.clear()
        for topic, event in pending:
            delivered += await self._ws_transport.broadcast(topic, event)
        return delivered

    def _wire_transport_handlers(self) -> None:
        async def on_subscribe(connection_id: str, topic: str) -> None:
            self.subscribe(connection_id, topic)

        async def on_unsubscribe(connection_id: str, topic: str) -> None:
            self.unsubscribe(connection_id, topic)

        def on_disconnect(conn, _reason: str) -> None:
            self.disconnect(conn.connection_id)

        self._ws_transport.on_subscribe(on_subscribe)
        self._ws_transport.on_unsubscribe(on_unsubscribe)
        self._ws_transport.on_disconnect(on_disconnect)

    def _client_id_for_connection(self, connection_id: str) -> str:
        conn = self._ws_transport.get_connection(connection_id)
        if conn is not None and conn.client_id:
            return conn.client_id
        return connection_id
