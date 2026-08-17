"""Shared notify.send dispatch: env URLs, store broadcast, and production adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rootseeker.channel_routing.notify_config import list_enabled_outbound_targets
from rootseeker.channel_routing.notify_env import resolve_notify_outbound_target
from rootseeker.channel_routing.outbound import (
    get_production_channel_registry,
    send_outbound_notification,
)
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.notification_channels import build_notification_channel_store

__all__ = ["dispatch_broadcast_notify", "dispatch_env_resolved_notify"]


def _resolve_repo_root(settings: RootSeekerSettings | None) -> Path:
    cfg = settings or RootSeekerSettings()
    root = Path(cfg.workspace_root)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


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


def dispatch_broadcast_notify(
    message: str,
    *,
    channel: str = "webhook",
    repo_root: Path | None = None,
    settings: RootSeekerSettings | None = None,
) -> dict[str, Any]:
    """Broadcast to enabled notification channels, or fall back to env-based single notify."""
    cfg = settings or RootSeekerSettings()
    root = repo_root or _resolve_repo_root(cfg)
    store = build_notification_channel_store(root, settings=cfg)
    store_settings = store.get_settings()
    if not store_settings.get("broadcast_enabled", True):
        return dispatch_env_resolved_notify(channel, message)

    targets = list_enabled_outbound_targets(store)
    if not targets:
        return {
            "ok": True,
            "channel": channel,
            "message": message,
            "error": None,
            "metadata": {
                "skipped": True,
                "reason": "no enabled notification channels configured",
                "broadcast": True,
            },
        }

    registry = get_production_channel_registry()
    results: list[dict[str, Any]] = []
    for target in targets:
        results.append(send_outbound_notification(target, message, registry=registry))

    failed = sum(1 for item in results if not item.get("ok"))
    sent = len(results) - failed
    return {
        "ok": failed == 0,
        "channel": channel,
        "message": message,
        "error": None if failed == 0 else f"{failed} notification channel(s) failed",
        "sent": sent,
        "failed": failed,
        "results": results,
        "metadata": {"broadcast": True},
    }
