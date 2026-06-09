from __future__ import annotations

from typing import Any

from rootseeker.channel_routing.inbound import ingest_channel_message
from rootseeker.channel_routing.models import ChannelMessage
from rootseeker.contracts.case import CaseCreateRequest

__all__ = ["webhook_payload_to_case_create"]


def webhook_payload_to_case_create(payload: dict[str, Any]) -> CaseCreateRequest:
    """Normalize webhook payload through channel routing pipeline into ``CaseCreateRequest``."""
    source = str(payload.get("source") or "webhook")
    normalized = ingest_channel_message(ChannelMessage(channel=source, payload=payload))
    metadata = dict(normalized.metadata)
    if normalized.trace_id:
        metadata["trace_id"] = normalized.trace_id
    metadata.setdefault("tenant", normalized.tenant)
    metadata.setdefault("environment", normalized.environment)
    metadata.setdefault("severity", normalized.severity)
    metadata.setdefault("team", normalized.team)
    return CaseCreateRequest(
        title=normalized.title,
        symptom=normalized.symptom,
        service_name=normalized.service_name,
        source=source,
        metadata=metadata,
    )
