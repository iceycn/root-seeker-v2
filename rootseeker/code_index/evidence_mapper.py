from __future__ import annotations

from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.evidence.builder import append_tool_json_evidence

__all__ = ["code_hits_to_evidence"]


def code_hits_to_evidence(
    *,
    pack: EvidencePack,
    tool_name: str,
    query: str,
    hits: list[dict],
) -> None:
    append_tool_json_evidence(
        pack,
        tool_name=tool_name,
        evidence_type=EvidenceType.CODE,
        content={"query": query, "hits": hits},
    )
