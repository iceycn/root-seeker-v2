"""Shared notify.send dispatch: resolve env URLs and use production channel adapters."""

from __future__ import annotations

from typing import Any

from rootseeker.channel_routing.notify_env import resolve_notify_outbound_target
from rootseeker.channel_routing.outbound import (
    get_production_channel_registry,
    send_outbound_notification,
)

__all__ = ["dispatch_env_resolved_notify"]


def dispatch_env_resolved_notify(channel: str, message: str) -> dict[str, Any]:
    """Send notification if an outbound URL is configured; otherwise skip with explicit metadata."""
    target = resolve_notify_outbound_target(channel)
    if target is None:
        return {
            "ok": True,
            "channel": channel,
            "message": message,
            "error": None,
            "metadata": {
                "skipped": True,
                "reason": (
                    "notify URL not configured: set ROOTSEEKER_NOTIFY_DEFAULT_URL or "
                    "ROOTSEEKER_NOTIFY_WEBHOOK_URL / FEISHU / etc."
                ),
            },
        }
    return send_outbound_notification(target, message, registry=get_production_channel_registry())
