from __future__ import annotations

from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.log_query import LogQueryResult
from rootseeker.evidence.builder import append_log_query_evidence

__all__ = ["log_result_to_evidence"]


def log_result_to_evidence(
    *,
    pack: EvidencePack,
    tool_name: str,
    result: LogQueryResult,
) -> None:
    append_log_query_evidence(pack, tool_name=tool_name, result=result)
