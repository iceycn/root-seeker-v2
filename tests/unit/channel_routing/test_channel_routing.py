import hmac
import json
from hashlib import sha256

from rootseeker.channel_routing import (
    ChannelMessage,
    ChannelRegistry,
    ChannelSecurity,
    OutboundTarget,
    RecordingChannelAdapter,
    build_session_key,
    ingest_channel_message,
    resolve_outbound_target,
    resolve_route,
    send_outbound_notification,
    webhook_payload_to_case_create,
)


def test_webhook_to_case_create_with_normalized_metadata() -> None:
    req = webhook_payload_to_case_create(
        {
            "title": "5xx spike",
            "message": "error ratio high",
            "service_name": "order-service",
            "source": "webhook",
            "tenant": "acme",
            "environment": "prod",
            "severity": "critical",
            "team": "order",
            "trace_id": "trace-1",
            "extra_key": "x",
        }
    )
    assert req.title == "5xx spike"
    assert req.service_name == "order-service"
    assert req.metadata["tenant"] == "acme"
    assert req.metadata["environment"] == "prod"
    assert req.metadata["trace_id"] == "trace-1"
    assert req.metadata["extra_key"] == "x"


def test_webhook_unwraps_sls_content_json_symptom() -> None:
    inner = (
        "2026-09-03 21:05:01.639 third-ability-service [SOFA-SEV-BOLT-BIZ-12200-10-T20] INFO  "
        "c.c.t.s.i.HarvardManageMentorCourseImpl - boom\n"
        "java.lang.NumberFormatException: For input string: \"user@example.com\"\n"
        "\tat com.coolcollege.thirdability.service.impl.HarvardManageMentorCourseImpl"
        ".getCourseProgress(HarvardManageMentorCourseImpl.java:169)\n"
    )
    req = webhook_payload_to_case_create(
        {
            "title": "错误排查请求",
            "message": json.dumps({"content": inner}),
            "source": "admin-error-chat",
        }
    )
    assert req.service_name == "third-ability-service"
    assert "HarvardManageMentorCourseImpl.java:169" in req.symptom
    assert not req.symptom.lstrip().startswith("{")


def test_routing_session_and_outbound_flow() -> None:
    msg = ChannelMessage(
        channel="webhook",
        payload={
            "title": "db timeout",
            "message": "latency high",
            "service_name": "payment-service",
            "tenant": "demo",
            "environment": "prod",
            "severity": "error",
            "team": "payment",
            "trace_id": "tr-xyz",
        },
    )
    normalized = ingest_channel_message(msg)
    route = resolve_route(normalized)
    session_key = build_session_key(normalized)
    target = resolve_outbound_target(route)

    capture = RecordingChannelAdapter()
    registry = ChannelRegistry()
    registry.register(capture)

    target = OutboundTarget(channel="recording", endpoint=target.endpoint, team=target.team)
    outbound = send_outbound_notification(target, "report ready", registry=registry)

    assert normalized.service_name == "payment-service"
    assert route.priority == "high"
    assert len(session_key) == 64
    assert outbound["ok"] is True
    assert outbound["channel"] == "recording"


def test_channel_security_allowlist_and_signature() -> None:
    payload = {"service_name": "api", "message": "boom"}
    secret = "abc123"
    signature = hmac.new(
        secret.encode("utf-8"),
        str(sorted(payload.items())).encode("utf-8"),
        sha256,
    ).hexdigest()
    msg = ChannelMessage(
        channel="webhook",
        payload=payload,
        headers={"x-signature": signature},
        remote_ip="10.0.0.1",
    )
    security = ChannelSecurity(allowlist_ips={"10.0.0.1"}, signing_secret=secret)
    normalized = ingest_channel_message(msg, security=security)
    assert normalized.service_name == "api"
