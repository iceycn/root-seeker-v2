from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rootseeker.contracts.case import CaseCreateRequest

__all__ = [
    "ToolPlan",
    "ToolPlanCall",
    "ToolPlanResult",
    "build_default_tool_arguments",
    "parse_tool_plan_content",
]


@dataclass(frozen=True)
class ToolPlanCall:
    tool_name: str
    step_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    depends_on: list[str] = field(default_factory=list)
    timeout_seconds: float | None = None
    required: bool = True

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "argument_keys": sorted(self.arguments.keys()),
            "rationale": self.rationale,
            "depends_on": list(self.depends_on),
            "required": self.required,
        }
        if self.timeout_seconds is not None:
            payload["timeout_seconds"] = self.timeout_seconds
        return payload

    def to_execution_metadata(self) -> dict[str, Any]:
        return {
            "depends_on": list(self.depends_on),
            "required": self.required,
            "timeout_seconds": self.timeout_seconds,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ToolPlan:
    tool_calls: list[ToolPlanCall]
    rationale: str = ""
    final_answer: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolPlanResult:
    ok: bool
    plan: ToolPlan | None = None
    provider: str | None = None
    model: str | None = None
    elapsed_ms: int | None = None
    raw_content: str = ""
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "elapsed_ms": self.elapsed_ms,
            "tool_call_count": len(self.plan.tool_calls) if self.plan is not None else 0,
        }
        if self.error:
            payload["error"] = self.error
        if self.plan is not None:
            payload["rationale"] = self.plan.rationale
            payload["tools"] = [call.tool_name for call in self.plan.tool_calls]
            payload["tool_calls"] = [call.to_payload() for call in self.plan.tool_calls]
        return {key: value for key, value in payload.items() if value is not None}


def parse_tool_plan_content(
    content: str,
    *,
    allowed_tools: set[str] | frozenset[str],
    max_tool_calls: int,
    case_request: CaseCreateRequest,
) -> ToolPlan | None:
    parsed = _parse_json_object(content)
    if parsed is None:
        return None

    calls_node = parsed.get("tool_calls")
    if not isinstance(calls_node, list):
        return None

    calls: list[ToolPlanCall] = []
    for idx, item in enumerate(calls_node[: max(0, max_tool_calls)]):
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
        if tool_name not in allowed_tools:
            continue
        raw_args = item.get("arguments")
        arguments = dict(raw_args) if isinstance(raw_args, dict) else {}
        arguments = build_default_tool_arguments(tool_name, case_request) | arguments
        step_id = str(item.get("step_id") or _step_id_from_tool(tool_name, idx)).strip()
        timeout_seconds = _parse_timeout_seconds(item.get("timeout_seconds"))
        calls.append(
            ToolPlanCall(
                tool_name=tool_name,
                step_id=step_id,
                arguments=arguments,
                rationale=str(item.get("rationale") or "").strip(),
                depends_on=_parse_string_list(item.get("depends_on")),
                timeout_seconds=timeout_seconds,
                required=_parse_bool(item.get("required", True)),
            )
        )

    if not calls:
        return None
    calls = _filter_dependencies(calls)
    final_answer = parsed.get("final_answer")
    return ToolPlan(
        tool_calls=calls,
        rationale=str(parsed.get("rationale") or "").strip(),
        final_answer=final_answer if isinstance(final_answer, str) else None,
        raw=parsed,
    )


def build_default_tool_arguments(tool_name: str, case_request: CaseCreateRequest) -> dict[str, Any]:
    trace_id = str(case_request.metadata.get("trace_id", "trace-unknown"))
    tenant = str(case_request.metadata.get("tenant", "demo"))
    environment = str(case_request.metadata.get("environment", "prod"))
    if tool_name == "catalog.resolve_service":
        return {"tenant": tenant, "environment": environment, "service_name": case_request.service_name}
    if tool_name == "catalog.get_log_sources":
        return {"tenant": tenant, "environment": environment, "service_name": case_request.service_name}
    if tool_name == "log.query_by_trace_id":
        return {"trace_id": trace_id, "service_name": case_request.service_name}
    if tool_name == "log.query_by_template":
        return {"template_id": "default.error_window", "service_name": case_request.service_name}
    if tool_name == "trace.get_chain":
        return {"trace_id": trace_id}
    if tool_name == "code.search":
        return {"query": case_request.symptom}
    if tool_name == "code.semantic_search":
        return {"query": case_request.symptom, "limit": 10}
    if tool_name == "code.read":
        return {"path": str(case_request.metadata.get("code_path", "README.md"))}
    return {}


def _parse_json_object(content: str) -> dict[str, Any] | None:
    text = _strip_code_fence(content.strip())
    for candidate in (text, _first_json_object(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _first_json_object(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else None


def _step_id_from_tool(tool_name: str, idx: int) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", tool_name).strip("-")
    return f"llm-{idx + 1}-{safe_name or 'tool'}"


def _parse_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _parse_timeout_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _filter_dependencies(calls: list[ToolPlanCall]) -> list[ToolPlanCall]:
    known_step_ids = {call.step_id for call in calls}
    filtered: list[ToolPlanCall] = []
    for call in calls:
        depends_on = [
            step_id
            for step_id in call.depends_on
            if step_id in known_step_ids and step_id != call.step_id
        ]
        filtered.append(
            ToolPlanCall(
                tool_name=call.tool_name,
                step_id=call.step_id,
                arguments=dict(call.arguments),
                rationale=call.rationale,
                depends_on=depends_on,
                timeout_seconds=call.timeout_seconds,
                required=call.required,
            )
        )
    return filtered
