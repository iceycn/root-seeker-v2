from __future__ import annotations

from hashlib import sha256

from rootseeker.channel_routing.models import NormalizedInboundMessage

__all__ = ["build_session_key"]


def build_session_key(message: NormalizedInboundMessage, *, include_team: bool = True) -> str:
    parts = [
        message.tenant,
        message.environment,
        message.service_name,
        message.severity,
    ]
    if include_team:
        parts.append(message.team)
    if message.trace_id:
        parts.append(message.trace_id)
    raw = "|".join(parts)
    return sha256(raw.encode("utf-8")).hexdigest()
