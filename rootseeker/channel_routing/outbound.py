from __future__ import annotations

from typing import Any

from rootseeker.channel_routing.adapter import ChannelRegistry
from rootseeker.channel_routing.models import OutboundTarget

__all__ = [
    "send_outbound_notification",
    "get_default_channel_registry",
    "get_production_channel_registry",
    "set_default_channel_registry",
]


def get_production_channel_registry() -> ChannelRegistry:
    """Registry with outbound adapters backed by HTTPS (Feishu, DingTalk, webhook, …)."""
    from rootseeker.channel_routing.adapters import (
        DingTalkChannelAdapter,
        DiscordChannelAdapter,
        FeishuChannelAdapter,
        SlackChannelAdapter,
        WebhookChannelAdapter,
        WeChatWorkAdapter,
    )

    reg = ChannelRegistry()
    reg.register(WebhookChannelAdapter())
    reg.register(FeishuChannelAdapter())
    reg.register(DingTalkChannelAdapter())
    reg.register(WeChatWorkAdapter())
    reg.register(SlackChannelAdapter())
    reg.register(DiscordChannelAdapter())
    return reg


_default_registry: ChannelRegistry | None = None


def get_default_channel_registry() -> ChannelRegistry:
    """Lazy singleton aligned with ``get_production_channel_registry`` (no in-process fake channels)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = get_production_channel_registry()
    return _default_registry


def set_default_channel_registry(registry: ChannelRegistry | None) -> None:
    """Set the default channel registry (for testing or custom setup)."""
    global _default_registry
    _default_registry = registry


def send_outbound_notification(
    target: OutboundTarget,
    message: str,
    registry: ChannelRegistry | None = None,
) -> dict[str, Any]:
    """Send a notification through the appropriate channel adapter.

    Args:
        target: The outbound target containing channel, endpoint, team, etc.
        message: The message content to send.
        registry: Optional channel registry. Uses default if not provided.

    Returns:
        A dict representation of the SendResult for backward compatibility.
    """
    reg = registry or get_default_channel_registry()
    result = reg.send(target, message)
    return {
        "ok": result.ok,
        "channel": result.channel,
        "message": result.message,
        "error": result.error,
        "metadata": result.metadata,
    }
