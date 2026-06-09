from __future__ import annotations

from rootseeker.channel_routing.models import ChannelMessage, NormalizedInboundMessage
from rootseeker.channel_routing.normalizer import normalize_inbound
from rootseeker.channel_routing.security import ChannelSecurity

__all__ = ["ingest_channel_message"]


def ingest_channel_message(
    message: ChannelMessage,
    *,
    security: ChannelSecurity | None = None,
) -> NormalizedInboundMessage:
    if security is not None:
        security.validate(message)
    return normalize_inbound(message)
