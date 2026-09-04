from __future__ import annotations

import re
from typing import Any

from rootseeker.analysis.call_chain import extract_exception_summary
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
                or _preferred_code_read_path(symptom)
            )
            if not path:
                return {
                    "_skip_reason": "No code search hit, explicit code_path, or file path in symptom."
                }
            payload: dict[str, Any] = {"path": str(path)}
            repo = service_name or _repo_from_code_search(step_outputs)
            if repo:
                payload["repo"] = repo
            from rootseeker.analysis.code_slice import chain_methods_for_path

            specs = chain_methods_for_path(str(path), _call_chain_for_code_read(step_outputs, symptom))
            if specs:
                payload["methods"] = [item["name"] for item in specs]
            line = int(specs[0].get("line") or 0) if specs else 0
            if not line:
                line = _fault_line_from_outputs(step_outputs, str(path)) or 0
            if line:
                payload["line"] = line
            return payload
        if action == "code.find_callers":
            call_chain = _call_chain_from_outputs(step_outputs)
            if not call_chain:
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
    channel = case_request.metadata.get("notify_channel", "webhook")
    return {
        "channel": channel,
        "message": _build_notify_message(case_request=case_request, report=report),
    }


_GENERIC_CASE_TITLES = frozenset({"", "t", "错误排查请求", "error triage", "case"})
_INDEXER_TAIL_RE = re.compile(
    r"(?:\s*;\s*)+(?:zoekt|gitnexus|qdrant|catalog)"
    r"(?:\s*;\s*(?:zoekt|gitnexus|qdrant|catalog))*\s*$",
    re.IGNORECASE,
)
_LOG_ERROR_PREFIX_RE = re.compile(r"^日志中发现错误:\s*")


def _build_notify_message(*, case_request: CaseCreateRequest, report: CaseReport) -> str:
    exception = extract_exception_summary(case_request.symptom, max_chars=180)
    cause = _clean_cause_title(
        report.root_cause.title if report.root_cause is not None else "",
        exception=exception,
    )
    headline = exception or cause or _usable_case_title(case_request.title) or "排查完成"
    service = resolve_service_name(
        case_request.service_name,
        text=case_request.symptom,
        default="",
    )
    if is_placeholder_service_name(service):
        service = ""

    lines = [f"【RootSeeker】{headline}"]
    if service:
        lines.append(f"服务：{service}")
    if cause and cause not in headline and headline not in cause:
        lines.append(f"结论：{cause}")
    narrative = ""
    if report.root_cause is not None:
        narrative = str(report.root_cause.narrative or "").strip()
    if narrative and narrative not in headline and narrative not in (cause or ""):
        if len(narrative) > 280:
            narrative = narrative[:277] + "..."
        lines.append(f"说明：{narrative}")
    confidence = report.root_cause.confidence if report.root_cause is not None else 0.0
    if confidence > 0:
        lines.append(f"置信度：{int(round(confidence * 100))}%")
    lines.append(f"Case：{report.case_id}")
    return "\n".join(lines)


def _usable_case_title(title: str) -> str:
    text = str(title or "").strip()
    if text.lower() in _GENERIC_CASE_TITLES or text in _GENERIC_CASE_TITLES:
        return ""
    return text


def _clean_cause_title(title: str, *, exception: str = "") -> str:
    text = _INDEXER_TAIL_RE.sub("", str(title or "").strip()).strip(" ;")
    text = _LOG_ERROR_PREFIX_RE.sub("", text).strip()
    if not text:
        return ""
    if exception and (text == exception or exception.startswith(text) or text.startswith(exception)):
        return ""
    return text


def _normalize_payload(step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    preferred: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    for step_id, payload in step_outputs.items():
        if not isinstance(payload, dict):
            continue
        extracted = payload.get("extracted")
        has_extracted = isinstance(extracted, dict)
        has_case = isinstance(payload.get("case_request"), dict)
        if not has_extracted and not has_case:
            continue
        if fallback is None:
            fallback = payload
        if "normalize" in str(step_id).lower() or has_case:
            preferred = payload
            break
    return preferred or fallback or {}


def _call_chain_from_outputs(step_outputs: dict[str, dict[str, Any]]) -> list[str]:
    extracted = _normalize_payload(step_outputs).get("extracted")
    if not isinstance(extracted, dict):
        return []
    call_chain = extracted.get("call_chain")
    if not isinstance(call_chain, list):
        return []
    return [str(item).strip() for item in call_chain if str(item).strip()]


def _call_chain_for_code_read(step_outputs: dict[str, dict[str, Any]], symptom: str) -> list[str]:
    chain = _call_chain_from_outputs(step_outputs)
    if chain:
        return chain
    from rootseeker.analysis.call_chain import extract_call_chain_summary

    return extract_call_chain_summary(str(symptom or ""))


def _normalized_case_request(step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    value = _normalize_payload(step_outputs).get("case_request")
    return value if isinstance(value, dict) else {}


def _symbol_from_call_chain(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    call_chain = _call_chain_from_outputs(step_outputs)
    if not call_chain:
        return None
    first = call_chain[0]
    return first.split(" (", 1)[0].strip() or None


def _path_from_normalized_input(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    extracted = _normalize_payload(step_outputs).get("extracted")
    if isinstance(extracted, dict) and extracted.get("code_path"):
        return str(extracted["code_path"])
    return None


def _symbol_from_symptom(symptom: str) -> str | None:
    text = str(symptom or "")
    match = re.search(r"\b([A-Z][\w$]+)\.([a-zA-Z_][\w$]*)\b", text)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
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


def _preferred_code_read_path(symptom: str) -> str | None:
    from rootseeker.analysis.call_chain import extract_code_path

    return extract_code_path(str(symptom or ""))


def _fault_line_from_outputs(step_outputs: dict[str, dict[str, Any]], path: str) -> int | None:
    from rootseeker.analysis.code_slice import fault_line_for_path

    return fault_line_for_path(path, _call_chain_from_outputs(step_outputs))
