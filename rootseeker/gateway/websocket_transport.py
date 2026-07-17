from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from rootseeker.contracts.common import new_id, utc_now
from rootseeker.gateway.protocol import GatewayEventFrame, GatewayRequestFrame, GatewayResponseFrame
from rootseeker.gateway.transport import GatewayTransport, TransportConnection, TransportMessage

__all__ = ["WebSocketTransport", "WebSocketConnectionState"]


@dataclass
class WebSocketConnectionState:
    """State tracked for each WebSocket connection."""

    connection_id: str
    websocket: WebSocket
    client_id: str | None = None
    remote_addr: str | None = None
    connected_at: datetime = field(default_factory=utc_now)
    last_ping_at: datetime = field(default_factory=utc_now)
    last_pong_at: datetime = field(default_factory=utc_now)
    subscriptions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


class WebSocketTransport(GatewayTransport):
    """WebSocket-based transport for Gateway.

    Features:
    - Full-duplex communication
    - Heartbeat/ping-pong for connection health
    - Automatic reconnection support
    - Topic-based subscription routing
    """

    def __init__(
        self,
        *,
        heartbeat_interval_seconds: float = 30.0,
        connection_timeout_seconds: float = 60.0,
        max_message_size_bytes: int = 1024 * 1024,  # 1MB
    ) -> None:
        self._connections: dict[str, WebSocketConnectionState] = {}
        self._client_id_map: dict[str, str] = {}  # client_id -> connection_id
        self._heartbeat_interval = heartbeat_interval_seconds
        self._connection_timeout = connection_timeout_seconds
        self._max_message_size = max_message_size_bytes
        self._lock = asyncio.Lock()

    async def accept(
        self,
        websocket: WebSocket,
        *,
        client_id: str | None = None,
        remote_addr: str | None = None,
    ) -> TransportConnection:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        connection_id = new_id("ws-")
        state = WebSocketConnectionState(
            connection_id=connection_id,
            websocket=websocket,
            client_id=client_id,
            remote_addr=remote_addr,
        )
        async with self._lock:
            self._connections[connection_id] = state
            if client_id:
                self._client_id_map[client_id] = connection_id

        conn = TransportConnection(
            connection_id=connection_id,
            client_id=client_id,
            remote_addr=remote_addr,
        )

        if self._on_connect_handler:
            self._on_connect_handler(conn)

        return conn

    async def send(self, connection_id: str, message: TransportMessage) -> None:
        """Send a message to a specific connection."""
        state = self._connections.get(connection_id)
        if state is None or not state.websocket:
            return

        try:
            if message.frame_type == "json":
                await state.websocket.send_json(message.payload)
            else:
                await state.websocket.send_text(json.dumps(message.payload))
        except Exception:
            # Connection likely closed
            await self.close(connection_id, reason="send_failed")

    async def broadcast(self, topic: str, event: GatewayEventFrame) -> int:
        """Broadcast an event to all subscribers of a topic."""
        delivered = 0
        to_remove: list[str] = []

        for connection_id, state in self._connections.items():
            if topic in state.subscriptions:
                try:
                    await state.websocket.send_json(event.model_dump(mode="json"))
                    delivered += 1
                except Exception:
                    to_remove.append(connection_id)

        # Clean up failed connections
        for conn_id in to_remove:
            await self.close(conn_id, reason="broadcast_failed")

        return delivered

    async def close(self, connection_id: str, reason: str = "") -> None:
        """Close a connection."""
        state = self._connections.get(connection_id)
        if state is None:
            return

        conn = TransportConnection(
            connection_id=connection_id,
            client_id=state.client_id,
            remote_addr=state.remote_addr,
            is_alive=False,
        )

        async with self._lock:
            self._connections.pop(connection_id, None)
            if state.client_id:
                self._client_id_map.pop(state.client_id, None)

        try:
            await state.websocket.close(code=1000, reason=reason[:120] if reason else "")
        except Exception:
            pass

        if self._on_disconnect_handler:
            self._on_disconnect_handler(conn, reason)

    def get_connection(self, connection_id: str) -> TransportConnection | None:
        """Get a connection by ID."""
        state = self._connections.get(connection_id)
        if state is None:
            return None
        return TransportConnection(
            connection_id=state.connection_id,
            client_id=state.client_id,
            remote_addr=state.remote_addr,
            metadata=state.metadata,
        )

    def list_connections(self) -> list[TransportConnection]:
        """List all active connections."""
        return [
            TransportConnection(
                connection_id=s.connection_id,
                client_id=s.client_id,
                remote_addr=s.remote_addr,
                metadata=s.metadata,
            )
            for s in self._connections.values()
        ]

    async def subscribe(self, connection_id: str, topic: str) -> None:
        """Subscribe a connection to a topic."""
        state = self._connections.get(connection_id)
        if state:
            state.subscriptions.add(topic)

    async def unsubscribe(self, connection_id: str, topic: str) -> None:
        """Unsubscribe a connection from a topic."""
        state = self._connections.get(connection_id)
        if state:
            state.subscriptions.discard(topic)

    async def handle_message(
        self,
        connection_id: str,
        data: dict[str, Any],
    ) -> GatewayRequestFrame | GatewayResponseFrame | None:
        """Handle an incoming message from a connection.

        Returns a response frame if the message is a request.
        """
        state = self._connections.get(connection_id)
        if state is None:
            return None

        frame_type = data.get("frame_type", "request")

        # Handle ping/pong for heartbeat
        if frame_type == "ping":
            state.last_ping_at = utc_now()
            await state.websocket.send_json(
                {"frame_type": "pong", "timestamp": utc_now().isoformat()}
            )
            return None

        if frame_type == "pong":
            state.last_pong_at = utc_now()
            return None

        # Handle subscribe/unsubscribe
        if frame_type == "subscribe":
            topic = str(data.get("topic", ""))
            if topic:
                await self.subscribe(connection_id, topic)
                await state.websocket.send_json({"frame_type": "subscribed", "topic": topic})
            return None

        if frame_type == "unsubscribe":
            topic = str(data.get("topic", ""))
            if topic:
                await self.unsubscribe(connection_id, topic)
                await state.websocket.send_json({"frame_type": "unsubscribed", "topic": topic})
            return None

        # Handle request/response
        if frame_type == "request":
            try:
                request = GatewayRequestFrame.model_validate(data)
                request.client_id = state.client_id

                if self._on_message_handler:
                    conn = self.get_connection(connection_id)
                    if conn:
                        self._on_message_handler(conn, TransportMessage(payload=data))

                return request
            except Exception:
                return GatewayResponseFrame(
                    request_id=data.get("request_id", "unknown"),
                    ok=False,
                    error={"code": "invalid_frame", "message": "Invalid request frame"},
                )

        return None

    async def receive_loop(self, connection_id: str) -> None:
        """Run the receive loop for a connection.

        This should be called in a background task after accept().
        """
        state = self._connections.get(connection_id)
        if state is None:
            return

        try:
            while True:
                data = await state.websocket.receive_json()
                await self.handle_message(connection_id, data)
        except WebSocketDisconnect:
            await self.close(connection_id, reason="client_disconnect")
        except Exception:
            await self.close(connection_id, reason="error")

    async def heartbeat_loop(self, connection_id: str) -> None:
        """Run heartbeat loop for a connection.

        Sends periodic pings and checks for pong responses.
        """
        state = self._connections.get(connection_id)
        if state is None:
            return

        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                if connection_id not in self._connections:
                    break

                # Send ping
                await state.websocket.send_json(
                    {"frame_type": "ping", "timestamp": utc_now().isoformat()}
                )
        except Exception:
            await self.close(connection_id, reason="heartbeat_failed")
