from __future__ import annotations

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.replay import ReplayCaseSpec

__all__ = ["default_replay_suite"]


def default_replay_suite() -> list[ReplayCaseSpec]:
    """Base benchmark set for default flow. Keeps >=10 cases per T18."""
    base = [
        ("rp-001", "order-service", "trace-order-001", "DB connection saturation"),
        ("rp-002", "api-gateway", "trace-api-002", "upstream timeout propagation"),
        ("rp-003", "order-service", "trace-order-003", "bad release config"),
        ("rp-004", "api-gateway", "trace-api-004", "cache miss storm"),
        ("rp-005", "order-service", "trace-order-005", "slow query amplification"),
        ("rp-006", "api-gateway", "trace-api-006", "ingress retry burst"),
        ("rp-007", "order-service", "trace-order-007", "thread pool exhaustion"),
        ("rp-008", "api-gateway", "trace-api-008", "rate limiter mis-tuned"),
        ("rp-009", "order-service", "trace-order-009", "message backlog"),
        ("rp-010", "api-gateway", "trace-api-010", "dependency TLS handshake delay"),
    ]
    items: list[ReplayCaseSpec] = []
    for replay_id, service, trace_id, root_cause in base:
        items.append(
            ReplayCaseSpec(
                replay_id=replay_id,
                name=f"{service} incident {replay_id}",
                alert_payload={
                    "title": f"{service} 5xx spike",
                    "message": "error ratio high",
                    "service_name": service,
                    "source": "replay-benchmark",
                    "tenant": "demo",
                    "environment": "prod",
                    "trace_id": trace_id,
                },
                case_request=CaseCreateRequest(
                    title=f"{service} 5xx spike",
                    symptom="error ratio high",
                    service_name=service,
                    source="replay-benchmark",
                    metadata={"trace_id": trace_id, "tenant": "demo", "environment": "prod"},
                ),
                log_samples=[{"trace_id": trace_id, "message": "sample log"}],
                trace_samples=[{"trace_id": trace_id, "spans": 3}],
                code_revision_hint="main@HEAD",
                human_root_cause=root_cause,
                expected_report_bullets=[service, "evidence", "notify"],
                redacted=True,
                metadata={"domain": "default-flow", "benchmark": "base"},
            )
        )
    return items
