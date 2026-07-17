from __future__ import annotations

import re
from typing import Any

from rootseeker.analysis.service_identity import is_placeholder_service_name, resolve_service_name
from rootseeker.code_index.search_query import build_zoekt_search_query
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
        symptom = str(normalized_case.get("symptom") or case_request.symptom)
        service_name = resolve_service_name(
            normalized_case.get("service_name"),
            case_request.service_name,
            text=symptom,
            default="",
        )
        trace_id = str(metadata.get("trace_id", "trace-unknown"))
        tenant = str(metadata.get("tenant", "demo"))
        environment = str(metadata.get("environment", "prod"))
        if action == "incident.normalize":
            payload = {
                **metadata,
                "title": case_request.title,
                "message": case_request.symptom,
                "source": case_request.source,
            }
            # Omit placeholder so normalize can infer from message text.
            if not is_placeholder_service_name(case_request.service_name):
                payload["service_name"] = case_request.service_name
            return {"payload": payload}
        if action == "catalog.resolve_service":
            return {
                "tenant": tenant,
                "environment": environment,
                "service_name": service_name or "unknown-service",
            }
        if action == "catalog.get_log_sources":
            return {
                "tenant": tenant,
                "environment": environment,
                "service_name": service_name or "unknown-service",
            }
        if action == "log.query_by_trace_id":
            payload = {"trace_id": trace_id}
            if service_name:
                payload["service_name"] = service_name
            return payload
        if action == "log.query_by_template":
            payload = {"template_id": "default.error_window"}
            if service_name:
                payload["service_name"] = service_name
            return payload
        if action == "trace.get_chain":
            return {"trace_id": trace_id}
        if action == "code.search":
            return {"query": _zoekt_search_query_from_symptom(symptom)}
        if action == "code.semantic_search":
            from rootseeker.code_index.search_query import extract_code_identifiers

            identifiers = extract_code_identifiers(symptom)
            query = " ".join(identifiers[:4]) if identifiers else symptom
            return {"query": query, "limit": 10}
        if action == "code.read":
            path = (
                _path_from_code_search(step_outputs)
                or metadata.get("code_path")
                or _path_from_normalized_input(step_outputs)
                or _path_from_symptom(symptom)
            )
            if not path:
                return {
                    "_skip_reason": "No code search hit, explicit code_path, or file path in symptom."
                }
            payload: dict[str, Any] = {"path": str(path)}
            repo = service_name or _repo_from_code_search(step_outputs)
            if repo:
                payload["repo"] = repo
            return payload
        if action == "code.find_callers":
            extracted = step_outputs.get("normalize-incident", {}).get("extracted")
            call_chain = extracted.get("call_chain") if isinstance(extracted, dict) else None
            if not isinstance(call_chain, list) or not call_chain:
                return {"_skip_reason": "No call_chain from normalize-incident."}
            payload = {
                "call_chain": call_chain,
                "max_depth": 5,
                "limit": 30,
                "prefer_graph": True,
            }
            if service_name:
                payload["service_name"] = service_name
            repo = service_name or _repo_from_code_search(step_outputs)
            if repo:
                payload["repo"] = repo
            return payload
        if action in {"graph.impact", "graph.context"}:
            symbol = _symbol_from_call_chain(step_outputs) or _symbol_from_symptom(symptom)
            if not symbol:
                return {"_skip_reason": "No fault symbol from call_chain or symptom."}
            payload = {"symbol": symbol}
            if action == "graph.impact":
                payload["direction"] = "upstream"
            repo = service_name or _repo_from_code_search(step_outputs)
            if repo:
                payload["repo"] = repo
            return payload
        if action == "graph.query":
            query = symptom.splitlines()[0].strip() if symptom else ""
            if not query:
                return {"_skip_reason": "No symptom text for graph.query."}
            payload = {"search_query": query[:200]}
            if service_name:
                payload["repo"] = service_name
            return payload
        if action in {"graph.list_repos", "index.get_status", "repo.list"}:
            return {}
        return {}


def build_notify_args(*, case_request: CaseCreateRequest, report: CaseReport) -> dict[str, Any]:
    cause_title = report.root_cause.title if report.root_cause is not None else "pending"
    channel = case_request.metadata.get("notify_channel", "webhook")
    service_name = resolve_service_name(
        case_request.service_name,
        text=case_request.symptom,
        default=case_request.service_name or "unknown-service",
    )
    return {
        "channel": channel,
        "message": (
            f"[{service_name}] {case_request.title} | "
            f"root_cause={cause_title} | evidence={len(report.evidence_item_ids)}"
        ),
    }


def _normalized_case_request(step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    value = step_outputs.get("normalize-incident", {}).get("case_request")
    return value if isinstance(value, dict) else {}


def _symbol_from_call_chain(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    extracted = step_outputs.get("normalize-incident", {}).get("extracted")
    if not isinstance(extracted, dict):
        return None
    call_chain = extracted.get("call_chain")
    if not isinstance(call_chain, list) or not call_chain:
        return None
    first = str(call_chain[0]).strip()
    if not first:
        return None
    return first.split(" (", 1)[0].strip() or None


def _symbol_from_symptom(symptom: str) -> str | None:
    text = str(symptom or "")
    match = re.search(r"\b([A-Z][\w$]+)\.([a-zA-Z_][\w$]*)\b", text)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return None


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
    return build_zoekt_search_query(symptom)


def _path_from_symptom(symptom: str) -> str | None:
    match = re.search(
        r"([A-Za-z0-9_./-]+\.(?:java|kt|py|go|ts|tsx|js|jsx|cs|rb|php|scala|rs|cpp|c|h))(?::\d+)?",
        symptom,
    )
    return match.group(1) if match else None
