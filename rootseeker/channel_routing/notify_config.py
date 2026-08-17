"""Map notification channel store records to outbound targets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rootseeker.channel_routing.models import OutboundTarget

if TYPE_CHECKING:
    from rootseeker.storage.notification_channels import NotificationChannelStore

__all__ = ["list_enabled_outbound_targets"]


def list_enabled_outbound_targets(store: NotificationChannelStore) -> list[OutboundTarget]:
    targets: list[OutboundTarget] = []
    for record in store.list_channels():
        if not record.get("enabled", True):
            continue
        endpoint = str(record.get("endpoint_url") or "").strip()
        if not endpoint:
            continue
        channel_type = str(record.get("channel_type") or "webhook")
        metadata = dict(record.get("metadata") or {})
        secret = str(record.get("secret") or "").strip()
        if secret:
            metadata["secret"] = secret
        targets.append(
            OutboundTarget(
                channel=channel_type,
                endpoint=endpoint,
                team="default",
                metadata=metadata,
            )
        )
    return targets
