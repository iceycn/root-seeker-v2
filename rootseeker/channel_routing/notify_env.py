"""Resolve notify.send outbound URLs from environment (no placeholder endpoints)."""

from __future__ import annotations

import os

from rootseeker.channel_routing.models import OutboundTarget

__all__ = ["resolve_notify_outbound_target"]

# ROOTSEEKER_NOTIFY_DEFAULT_URL applies when a channel-specific variable is unset.
_CHANNEL_ENV_KEYS: dict[str, str] = {
    "webhook": "ROOTSEEKER_NOTIFY_WEBHOOK_URL",
    "feishu": "ROOTSEEKER_NOTIFY_FEISHU_URL",
    "dingtalk": "ROOTSEEKER_NOTIFY_DINGTALK_URL",
    "wechat": "ROOTSEEKER_NOTIFY_WECHAT_URL",
    # ChannelAdapter uses "wechat_work"; keep separate from generic "wechat".
    "wechat_work": "ROOTSEEKER_NOTIFY_WECHAT_WORK_URL",
    "slack": "ROOTSEEKER_NOTIFY_SLACK_URL",
    "discord": "ROOTSEEKER_NOTIFY_DISCORD_URL",
}

# Short names used in .env.example / common ops (no ROOTSEEKER_ prefix).
_CHANNEL_LEGACY_ENV_FALLBACKS: dict[str, str] = {
    "wechat_work": "WECHAT_WORK_WEBHOOK_URL",
    "feishu": "FEISHU_WEBHOOK_URL",
    "dingtalk": "DINGTALK_WEBHOOK_URL",
    "slack": "SLACK_WEBHOOK_URL",
    "discord": "DISCORD_WEBHOOK_URL",
}


def resolve_notify_outbound_target(channel: str) -> OutboundTarget | None:
    """Return a target with a real HTTPS URL, or None if nothing is configured."""
    raw = ""
    env_key = _CHANNEL_ENV_KEYS.get(channel)
    if env_key:
        raw = os.getenv(env_key, "") or ""
    if not raw.strip():
        legacy = _CHANNEL_LEGACY_ENV_FALLBACKS.get(channel)
        if legacy:
            raw = os.getenv(legacy, "") or ""
    if not raw.strip():
        raw = os.getenv("ROOTSEEKER_NOTIFY_DEFAULT_URL", "") or ""
    raw = raw.strip()
    if not raw:
        return None
    return OutboundTarget(
        channel=channel,
        endpoint=raw,
        team=os.getenv("ROOTSEEKER_NOTIFY_TEAM", "default"),
        metadata={},
    )
