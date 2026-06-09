from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rootseeker.contracts.common import utc_now

__all__ = ["PresenceRegistry", "PresenceRecord"]


@dataclass
class PresenceRecord:
    node_id: str
    role: str
    last_seen_at: datetime
    metadata: dict[str, str]


class PresenceRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, PresenceRecord] = {}

    def heartbeat(self, *, node_id: str, role: str, metadata: dict[str, str] | None = None) -> None:
        self._nodes[node_id] = PresenceRecord(
            node_id=node_id,
            role=role,
            last_seen_at=utc_now(),
            metadata=dict(metadata or {}),
        )

    def list_nodes(self) -> list[PresenceRecord]:
        return list(self._nodes.values())
