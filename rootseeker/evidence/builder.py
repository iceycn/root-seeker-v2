from __future__ import annotations

from typing import Any

from rootseeker.contracts.common import new_id
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, EvidenceType
from rootseeker.contracts.log_query import LogQueryResult

__all__ = ["append_log_query_evidence", "append_tool_json_evidence"]


def append_log_query_evidence(
    pack: EvidencePack,
    *,
    tool_name: str,
    result: LogQueryResult,
) -> EvidenceItem:
    item = EvidenceItem(
        item_id=new_id("ev-"),
        type=EvidenceType.LOG,
        source=tool_name,
        content={
            "query_key": result.query_key,
            "truncated": result.truncated,
            "record_count": len(result.records),
            "metadata": result.metadata,
        },
    )
    pack.items.append(item)
    return item


def append_tool_json_evidence(
    pack: EvidencePack,
    *,
    tool_name: str,
    evidence_type: EvidenceType,
    content: dict[str, Any],
) -> EvidenceItem:
    item = EvidenceItem(
        item_id=new_id("ev-"),
        type=evidence_type,
        source=tool_name,
        content=content,
    )
    pack.items.append(item)
    return item
