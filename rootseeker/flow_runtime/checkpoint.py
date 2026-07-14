from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rootseeker.contracts.common import utc_now

__all__ = ["FlowCheckpointRecord", "FlowCheckpointStore"]


@dataclass
class FlowCheckpointRecord:
    flow_run_id: str
    revision: int
    payload: dict[str, Any]
    updated_at: datetime


@dataclass
class FlowCheckpointStore:
    _items: dict[str, FlowCheckpointRecord] = field(default_factory=dict)

    def save(self, flow_run_id: str, payload: dict[str, Any]) -> None:
        existing = self._items.get(flow_run_id)
        revision = 1 if existing is None else existing.revision + 1
        self._items[flow_run_id] = FlowCheckpointRecord(
            flow_run_id=flow_run_id,
            revision=revision,
            payload=dict(payload),
            updated_at=utc_now(),
        )

    def get(self, flow_run_id: str) -> dict[str, Any] | None:
        record = self._items.get(flow_run_id)
        return None if record is None else dict(record.payload)

    def get_record(self, flow_run_id: str) -> FlowCheckpointRecord | None:
        return self._items.get(flow_run_id)

    def list_records(
        self,
        *,
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[FlowCheckpointRecord]:
        records = list(self._items.values())
        if case_id is not None:
            records = [r for r in records if r.payload.get("case_id") == case_id]
        if status is not None:
            records = [r for r in records if r.payload.get("status") == status]
        records.sort(key=lambda r: r.updated_at)
        if limit < 0:
            return records
        return records[-limit:]

    def count(self) -> int:
        return len(self._items)
