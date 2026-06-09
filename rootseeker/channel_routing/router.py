from __future__ import annotations

from rootseeker.channel_routing.models import NormalizedInboundMessage, ResolvedRoute

__all__ = ["resolve_route"]


def resolve_route(message: NormalizedInboundMessage) -> ResolvedRoute:
    priority = "high" if message.severity.lower() in {"critical", "error", "sev1"} else "normal"
    return ResolvedRoute(
        channel=message.channel,
        tenant=message.tenant,
        team=message.team,
        priority=priority,
        labels={
            "service_name": message.service_name,
            "environment": message.environment,
            "severity": message.severity,
        },
    )
