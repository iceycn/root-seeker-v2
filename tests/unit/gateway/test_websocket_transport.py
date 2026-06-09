from __future__ import annotations

import pytest

from rootseeker.gateway import TransportMessage, WebSocketTransport


def test_websocket_transport_initialization() -> None:
    transport = WebSocketTransport(
        heartbeat_interval_seconds=10.0,
        connection_timeout_seconds=30.0,
    )
    assert transport._heartbeat_interval == 10.0
    assert transport._connection_timeout == 30.0


def test_websocket_transport_list_connections_empty() -> None:
    transport = WebSocketTransport()
    connections = transport.list_connections()
    assert connections == []


def test_websocket_transport_get_connection_not_found() -> None:
    transport = WebSocketTransport()
    conn = transport.get_connection("nonexistent")
    assert conn is None


@pytest.mark.asyncio
async def test_websocket_transport_broadcast_empty() -> None:
    """Test broadcast when no connections exist."""
    from rootseeker.gateway.protocol import GatewayEventFrame

    transport = WebSocketTransport()
    event = GatewayEventFrame(topic="test.topic", payload={"key": "value"})
    delivered = await transport.broadcast("test.topic", event)
    assert delivered == 0


@pytest.mark.asyncio
async def test_websocket_transport_close_nonexistent() -> None:
    """Test closing a non-existent connection is safe."""
    transport = WebSocketTransport()
    await transport.close("nonexistent", reason="test")  # Should not raise


def test_transport_message_creation() -> None:
    msg = TransportMessage(payload={"test": "data"}, frame_type="json")
    assert msg.payload == {"test": "data"}
    assert msg.frame_type == "json"


def test_websocket_transport_on_connect_handler() -> None:
    """Test that on_connect handler can be registered."""
    transport = WebSocketTransport()
    called = []

    def handler(conn):
        called.append(conn.connection_id)

    transport.on_connect(handler)
    assert transport._on_connect_handler is not None


def test_websocket_transport_on_disconnect_handler() -> None:
    """Test that on_disconnect handler can be registered."""
    transport = WebSocketTransport()
    called = []

    def handler(conn, reason):
        called.append((conn.connection_id, reason))

    transport.on_disconnect(handler)
    assert transport._on_disconnect_handler is not None


def test_websocket_transport_on_message_handler() -> None:
    """Test that on_message handler can be registered."""
    transport = WebSocketTransport()
    called = []

    def handler(conn, msg):
        called.append((conn.connection_id, msg.payload))

    transport.on_message(handler)
    assert transport._on_message_handler is not None
