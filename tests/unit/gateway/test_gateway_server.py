from rootseeker.gateway import (
    GatewayEventFrame,
    GatewayFrameType,
    GatewayRequestFrame,
    GatewayServer,
)


def test_gateway_protocol_frames() -> None:
    req = GatewayRequestFrame(method="system.ping")
    assert req.frame_type == GatewayFrameType.REQUEST
    assert GatewayFrameType.PING == "ping"
    assert GatewayFrameType.CONNECTED == "connected"
    event = GatewayEventFrame(topic="case.changed", payload={"case_id": "c1"})
    assert event.frame_type == GatewayFrameType.EVENT


def test_gateway_request_response_and_method_registry() -> None:
    server = GatewayServer()
    payload = {"method": "system.ping", "params": {}}
    response = server.handle_http_request(payload)
    assert response["ok"] is True
    assert response["result"]["pong"] is True

    fail = server.handle_http_request({"method": "unknown.method", "params": {}})
    assert fail["ok"] is False
    assert fail["error"]["code"] == "method_not_found"


def test_gateway_subscribe_and_broadcast() -> None:
    server = GatewayServer()
    c1 = server.connect()
    c2 = server.connect()

    subscribe_resp = server.handle_http_request(
        {
            "method": "gateway.subscribe",
            "params": {"client_id": c1.client_id, "topic": "case.*"},
        }
    )
    assert subscribe_resp["ok"] is True
    assert "case.*" in subscribe_resp["result"]["topics"]

    server.handle_http_request(
        {
            "method": "gateway.subscribe",
            "params": {"client_id": c2.client_id, "topic": "tool.called"},
        }
    )

    result = server.publish("case.changed", {"case_id": "c1"})
    assert result["delivered_count"] == 1

    c1_events = server.poll_events(c1.client_id)
    c2_events = server.poll_events(c2.client_id)
    assert len(c1_events) == 1
    assert c1_events[0]["topic"] == "case.changed"
    assert c2_events == []


def test_gateway_unsubscribe() -> None:
    server = GatewayServer()
    c1 = server.connect()
    server.handle_http_request(
        {
            "method": "gateway.subscribe",
            "params": {"client_id": c1.client_id, "topic": "agent.event"},
        }
    )
    server.handle_http_request(
        {
            "method": "gateway.unsubscribe",
            "params": {"client_id": c1.client_id, "topic": "agent.event"},
        }
    )
    result = server.publish("agent.event", {"k": "v"})
    assert result["delivered_count"] == 0
