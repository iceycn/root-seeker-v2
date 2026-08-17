from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rootseeker.gateway import GatewayServer, WebSocketTransport
from rootseeker.gateway.websocket_transport import WebSocketConnectionState
from rootseeker.gateway.ws_bridge import GatewayWsBridge


@pytest.mark.asyncio
async def test_gateway_ws_bridge_subscribe_syncs_registry_and_broadcasts() -> None:
    server = GatewayServer()
    transport = WebSocketTransport()
    bridge = GatewayWsBridge(server, transport)

    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock()
    connection_id = "ws-test-1"
    transport._connections[connection_id] = WebSocketConnectionState(
        connection_id=connection_id,
        websocket=mock_ws,
    )

    client_id = bridge.ensure_client(connection_id)
    bridge.subscribe(connection_id, "case.*")

    assert "case.*" in server.subscriptions.list_topics(client_id)
    assert "case.*" in transport._connections[connection_id].subscriptions

    bridge.queue_broadcast("case.c1", {"case_id": "c1"})
    delivered = await bridge.flush_broadcasts()
    assert delivered == 1
    mock_ws.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_gateway_ws_bridge_publish_updates_gateway_inbox() -> None:
    server = GatewayServer()
    transport = WebSocketTransport()
    bridge = GatewayWsBridge(server, transport)

    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock()
    connection_id = "ws-test-2"
    transport._connections[connection_id] = WebSocketConnectionState(
        connection_id=connection_id,
        websocket=mock_ws,
    )

    client_id = bridge.ensure_client(connection_id)
    bridge.subscribe(connection_id, "case.*")

    result = bridge.publish("case.c2", {"case_id": "c2"})
    assert result["delivered_count"] == 1

    events = server.poll_events(client_id)
    assert len(events) == 1
    assert events[0]["topic"] == "case.c2"

    delivered = await bridge.flush_broadcasts()
    assert delivered == 1


def test_gateway_ws_bridge_disconnect_removes_client() -> None:
    server = GatewayServer()
    transport = WebSocketTransport()
    bridge = GatewayWsBridge(server, transport)

    connection_id = "ws-test-3"
    transport._connections[connection_id] = WebSocketConnectionState(
        connection_id=connection_id,
        websocket=MagicMock(),
    )

    client_id = bridge.ensure_client(connection_id)
    bridge.subscribe(connection_id, "agent.event")
    bridge.disconnect(connection_id)

    assert client_id not in server.connections
    assert server.subscriptions.list_topics(client_id) == []
