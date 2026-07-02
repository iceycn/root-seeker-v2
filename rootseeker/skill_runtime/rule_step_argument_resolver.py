from __future__ import annotations

import re
from typing import Any

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.report import CaseReport

__all__ = ["RuleStepArgumentResolver", "build_notify_args"]


class RuleStepArgumentResolver:
    """Deterministic fallback argument resolver (legacy runner logic)."""

    def resolve(
        self,
        action: str,
        case_request: CaseCreateRequest,
        *,
        step_outputs: dict[str, dict[str, Any]] | None = None,
        report: CaseReport | None = None,
    ) -> dict[str, Any]:
        outputs = step_outputs or {}
        if action == "notify.send" and report is not None:
            return build_notify_args(case_request=case_request, report=report)
        args = self._build_step_args(action, case_request, step_outputs=outputs)
        return args

    def _build_step_args(
        self,
        action: str,
        case_request: CaseCreateRequest,
        *,
        step_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_case = _normalized_case_request(step_outputs)
        metadata = dict(case_request.metadata)
        normalized_metadata = normalized_case.get("metadata")
        if isinstance(normalized_metadata, dict):
            metadata.update(normalized_metadata)
        service_name = str(normalized_case.get("service_name") or case_request.service_name)
        symptom = str(normalized_case.get("symptom") or case_request.symptom)
        trace_id = str(metadata.get("trace_id", "trace-unknown"))
        tenant = str(metadata.get("tenant", "demo"))
        environment = str(metadata.get("environment", "prod"))
        if action == "incident.normalize":
            payload = {
                **metadata,
                "title": case_request.title,
                "service_name": case_request.service_name,
                "message": case_request.symptom,
                "source": case_request.source,
            }
            return {"payload": payload}
        if action == "catalog.resolve_service":
            return {"tenant": tenant, "environment": environment, "service_name": service_name}
        if action == "catalog.get_log_sources":
            return {"tenant": tenant, "environment": environment, "service_name": service_name}
        if action == "log.query_by_trace_id":
            return {"trace_id": trace_id, "service_name": service_name}
        if action == "log.query_by_template":
            return {"template_id": "default.error_window", "service_name": service_name}
        if action == "trace.get_chain":
            return {"trace_id": trace_id}
        if action == "code.search":
            return {"query": _zoekt_search_query_from_symptom(symptom)}
        if action == "code.semantic_search":
            return {"query": symptom, "limit": 10}
        if action == "code.read":
            path = (
                _path_from_code_search(step_outputs)
                or metadata.get("code_path")
                or _path_from_normalized_input(step_outputs)
                or _path_from_symptom(symptom)
            )
            if not path:
                return {"_skip_reason": "No code search hit, explicit code_path, or file path in symptom."}
            payload: dict[str, Any] = {"path": str(path)}
            repo = _repo_from_code_search(step_outputs)
            if repo:
                payload["repo"] = repo
            return payload
        if action in {"index.get_status", "repo.list"}:
            return {}
        return {}


def build_notify_args(*, case_request: CaseCreateRequest, report: CaseReport) -> dict[str, Any]:
    cause_title = report.root_cause.title if report.root_cause is not None else "pending"
    channel = case_request.metadata.get("notify_channel", "webhook")
    return {
        "channel": channel,
        "message": (
            f"[{case_request.service_name}] {case_request.title} | "
            f"root_cause={cause_title} | evidence={len(report.evidence_item_ids)}"
        ),
    }


def _normalized_case_request(step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    value = step_outputs.get("normalize-incident", {}).get("case_request")
    return value if isinstance(value, dict) else {}


def _path_from_normalized_input(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    extracted = step_outputs.get("normalize-incident", {}).get("extracted")
    if isinstance(extracted, dict) and extracted.get("code_path"):
        return str(extracted["code_path"])
    return None


def _path_from_code_search(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    hits = step_outputs.get("code-search", {}).get("hits")
    if not isinstance(hits, list):
        return None
    for hit in hits:
        if isinstance(hit, dict) and hit.get("path"):
            return str(hit["path"])
    return None


def _repo_from_code_search(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    hits = step_outputs.get("code-search", {}).get("hits")
    if not isinstance(hits, list):
        return None
    for hit in hits:
        if isinstance(hit, dict) and hit.get("repo"):
            return str(hit["repo"])
    return None


def _zoekt_search_query_from_symptom(symptom: str) -> str:
    path = _path_from_symptom(symptom)
    if path:
        return f"file:{path}"
    first_line = symptom.strip().splitlines()[0] if symptom.strip() else symptom
    return " ".join(first_line.split())


def _path_from_symptom(symptom: str) -> str | None:
    match = re.search(
        r"([A-Za-z0-9_./-]+\.(?:java|kt|py|go|ts|tsx|js|jsx|cs|rb|php|scala|rs|cpp|c|h))(?::\d+)?",
        symptom,
    )
    return match.group(1) if match else None
