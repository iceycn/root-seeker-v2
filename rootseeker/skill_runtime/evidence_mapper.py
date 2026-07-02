from __future__ import annotations

from typing import Any

from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.contracts.log_query import LogQueryResult
from rootseeker.contracts.skill import SkillSpec
from rootseeker.evidence import append_log_query_evidence, append_tool_json_evidence

__all__ = ["map_tool_result_to_evidence"]


_ACTION_EVIDENCE_TYPES: dict[str, EvidenceType] = {
    "incident.normalize": EvidenceType.OTHER,
    "log.query_by_trace_id": EvidenceType.LOG,
    "log.query_by_template": EvidenceType.LOG,
    "trace.get_chain": EvidenceType.TRACE,
    "code.search": EvidenceType.CODE,
    "code.read": EvidenceType.CODE,
    "index.get_status": EvidenceType.OTHER,
    "repo.list": EvidenceType.CODE,
    "catalog.resolve_service": EvidenceType.SERVICE_CATALOG,
    "catalog.get_log_sources": EvidenceType.SERVICE_CATALOG,
}


def map_tool_result_to_evidence(
    *,
    pack: EvidencePack,
    action: str,
    content: dict[str, Any],
    tool_skill: SkillSpec | None = None,
) -> None:
    evidence_type = _evidence_type_for_action(action, tool_skill)
    if evidence_type is None:
        return
    if action == "log.query_by_trace_id":
        log_result = LogQueryResult.model_validate(content)
        append_log_query_evidence(pack, tool_name=action, result=log_result)
        return
    append_tool_json_evidence(pack, tool_name=action, evidence_type=evidence_type, content=content)


def _evidence_type_for_action(action: str, tool_skill: SkillSpec | None) -> EvidenceType | None:
    by_action = _ACTION_EVIDENCE_TYPES.get(action)
    if by_action is not None:
        return by_action
    if tool_skill is not None:
        raw = tool_skill.metadata.get("evidence_type")
        if raw == "none":
            return None
        if isinstance(raw, str) and raw:
            try:
                return EvidenceType(raw)
            except ValueError:
                pass
    if action.startswith("log."):
        return EvidenceType.LOG
    if action.startswith("trace."):
        return EvidenceType.TRACE
    if action.startswith("code."):
        return EvidenceType.CODE
    if action.startswith("catalog."):
        return EvidenceType.SERVICE_CATALOG
    return EvidenceType.OTHER
