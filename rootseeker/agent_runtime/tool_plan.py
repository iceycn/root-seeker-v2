from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.skill_runtime.rule_step_argument_resolver import RuleStepArgumentResolver

__all__ = [
    "ToolPlan",
    "ToolPlanCall",
    "ToolPlanResult",
    "build_default_tool_arguments",
    "enrich_tool_arguments_with_step_outputs",
    "parse_tool_plan_content",
]

_rule_resolver = RuleStepArgumentResolver()


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
        arguments = _normalize_planned_arguments(tool_name, arguments)
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
    calls = _require_normalize_dependency(calls)
    final_answer = parsed.get("final_answer")
    return ToolPlan(
        tool_calls=calls,
        rationale=str(parsed.get("rationale") or "").strip(),
        final_answer=final_answer if isinstance(final_answer, str) else None,
        raw=parsed,
    )


def build_default_tool_arguments(tool_name: str, case_request: CaseCreateRequest) -> dict[str, Any]:
    return _rule_resolver.resolve(tool_name, case_request, step_outputs={})


def enrich_tool_arguments_with_step_outputs(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    case_request: CaseCreateRequest,
    step_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Fill planned args from completed steps (e.g. normalize call_chain)."""
    defaults = _rule_resolver.resolve(tool_name, case_request, step_outputs=step_outputs)
    merged = dict(defaults)
    merged.update(arguments or {})
    if tool_name == "code.find_callers":
        chain = merged.get("call_chain")
        usable = isinstance(chain, list) and any(str(item).strip() for item in chain)
        if not usable:
            default_chain = defaults.get("call_chain")
            if isinstance(default_chain, list) and default_chain:
                merged["call_chain"] = default_chain
                usable = True
        if usable:
            merged.pop("_skip_reason", None)
    elif tool_name in {"graph.impact", "graph.context"}:
        if not str(merged.get("symbol") or "").strip():
            default_symbol = str(defaults.get("symbol") or "").strip()
            if default_symbol:
                merged["symbol"] = default_symbol
        if str(merged.get("symbol") or "").strip():
            merged.pop("_skip_reason", None)
    elif tool_name == "code.read":
        if str(merged.get("path") or merged.get("file_path") or "").strip():
            merged.pop("_skip_reason", None)
        from rootseeker.analysis.code_slice import chain_methods_for_path, fault_line_for_path
        from rootseeker.skill_runtime.rule_step_argument_resolver import (
            _call_chain_for_code_read,
        )

        path = str(merged.get("path") or merged.get("file_path") or "")
        chain = _call_chain_for_code_read(step_outputs, str(case_request.symptom or ""))
        specs = chain_methods_for_path(path, chain)
        if specs:
            merged["methods"] = [item["name"] for item in specs]
            if specs[0].get("line"):
                merged["line"] = int(specs[0]["line"])
        else:
            methods = _coerce_code_read_methods(merged)
            if methods:
                merged["methods"] = methods
        if not merged.get("line") and not merged.get("focus_line"):
            line = fault_line_for_path(path, chain) or 0
            if line:
                merged["line"] = line
    return _normalize_planned_arguments(tool_name, merged)


def _normalize_planned_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name != "code.read":
        return arguments
    out = dict(arguments)
    explicit = str(out.get("file_path") or out.get("file") or "").strip()
    path = str(out.get("path") or "").strip()
    if explicit and (not path or path != explicit):
        out["path"] = explicit
    methods = _coerce_code_read_methods(out)
    if methods:
        out["methods"] = methods
    return out


def _coerce_code_read_methods(arguments: dict[str, Any]) -> list[str]:
    raw = arguments.get("methods")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        names = [str(item).strip() for item in raw if str(item).strip()]
        if names:
            return names
    for key in ("focus_method", "method", "method_name"):
        alias = arguments.get(key)
        if isinstance(alias, str) and alias.strip():
            return [alias.strip()]
        if isinstance(alias, list):
            names = [str(item).strip() for item in alias if str(item).strip()]
            if names:
                return names
    return []


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


_CHAIN_DEPENDENT_TOOLS = {"code.read", "code.find_callers"}


def _require_normalize_dependency(calls: list[ToolPlanCall]) -> list[ToolPlanCall]:
    normalize_ids = [call.step_id for call in calls if call.tool_name == "incident.normalize"]
    if not normalize_ids:
        return calls
    normalize_id = normalize_ids[0]
    required: list[ToolPlanCall] = []
    for call in calls:
        depends_on = list(call.depends_on)
        if (
            call.tool_name in _CHAIN_DEPENDENT_TOOLS
            and call.step_id != normalize_id
            and normalize_id not in depends_on
        ):
            depends_on.append(normalize_id)
        required.append(
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
    return required
