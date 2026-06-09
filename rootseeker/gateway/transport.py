from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rootseeker.gateway.protocol import GatewayEventFrame

__all__ = ["GatewayTransport", "TransportConnection", "TransportMessage"]


@dataclass
class TransportMessage:
    """Message sent/received through transport."""

    payload: dict[str, Any]
    frame_type: str = "json"  # json, binary, text


@dataclass
class TransportConnection:
    """Represents a transport-level connection."""

    connection_id: str
    client_id: str | None = None
    remote_addr: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    is_alive: bool = True


class GatewayTransport(ABC):
    """Abstract transport layer for Gateway.

    Implementations can be WebSocket, SSE, HTTP long-polling, etc.
    """

    @abstractmethod
    async def send(self, connection_id: str, message: TransportMessage) -> None:
        """Send a message to a specific connection."""
        ...

    @abstractmethod
    async def broadcast(self, topic: str, event: GatewayEventFrame) -> int:
        """Broadcast an event to all subscribers of a topic.

        Returns the number of connections that received the event.
        """
        ...

    @abstractmethod
    async def close(self, connection_id: str, reason: str = "") -> None:
        """Close a connection."""
        ...

    @abstractmethod
    def get_connection(self, connection_id: str) -> TransportConnection | None:
        """Get a connection by ID."""
        ...

    @abstractmethod
    def list_connections(self) -> list[TransportConnection]:
        """List all active connections."""
        ...

    def on_connect(self, handler: Callable[[TransportConnection], None]) -> None:
        """Register a handler for new connections."""
        self._on_connect_handler = handler

    def on_disconnect(self, handler: Callable[[TransportConnection, str], None]) -> None:
        """Register a handler for disconnections."""
        self._on_disconnect_handler = handler

    def on_message(self, handler: Callable[[TransportConnection, TransportMessage], None]) -> None:
        """Register a handler for incoming messages."""
        self._on_message_handler = handler

    _on_connect_handler: Callable[[TransportConnection], None] | None = None
    _on_disconnect_handler: Callable[[TransportConnection, str], None] | None = None
    _on_message_handler: Callable[[TransportConnection, TransportMessage], None] | None = None
