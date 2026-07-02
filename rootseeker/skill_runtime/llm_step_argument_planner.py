from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from rootseeker.analysis.llm_report import LlmReportConfig, OpenAICompatibleReportClient
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.tool import ToolSpec
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.skill_system.content_loader import SkillStepContext

__all__ = [
    "LlmStepArgumentPlanner",
    "OpenAICompatibleStepArgumentPlanner",
    "StepArgumentPlan",
    "build_step_argument_messages",
    "parse_step_argument_content",
]


@dataclass
class StepArgumentPlan:
    arguments: dict[str, Any]
    skip: bool = False
    skip_reason: str = ""
    rationale: str = ""
    argument_source: str = "llm"

    def to_step_metadata(self) -> dict[str, Any]:
        return {
            "argument_source": self.argument_source,
            "rationale": self.rationale,
            "skip": self.skip,
            "skip_reason": self.skip_reason,
        }


def build_step_argument_messages(
    *,
    case_request: CaseCreateRequest,
    action: str,
    tool_spec: ToolSpec,
    skill_context: SkillStepContext,
    step_outputs: dict[str, dict[str, Any]],
    report_summary: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "task": "Generate arguments for a single MCP tool call in a troubleshooting flow.",
        "action": action,
        "tool": {
            "name": tool_spec.name,
            "description": tool_spec.description,
            "parameters_schema": tool_spec.parameters_schema,
        },
        "case": case_request.model_dump(mode="json"),
        "prior_step_outputs": step_outputs,
        "report_summary": report_summary,
        "output_schema": {
            "skip": "boolean — true when the step should be skipped",
            "skip_reason": "string when skip is true",
            "rationale": "short string explaining argument choices",
            "arguments": "object matching parameters_schema when skip is false",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "你是 RootSeeker 工具参数规划器。根据工具 Skill 文档、Case 与前序步骤输出，"
                "为当前单步工具调用生成 JSON。只输出一个 JSON 对象，不要 Markdown。"
            ),
        },
        {"role": "user", "content": skill_context.to_prompt_text()},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]


def parse_step_argument_content(content: str) -> StepArgumentPlan | None:
    parsed = _parse_json_object(content)
    if parsed is None:
        return None
    skip = bool(parsed.get("skip"))
    skip_reason = str(parsed.get("skip_reason") or "").strip()
    rationale = str(parsed.get("rationale") or "").strip()
    raw_args = parsed.get("arguments")
    arguments = dict(raw_args) if isinstance(raw_args, dict) else {}
    return StepArgumentPlan(
        arguments=arguments,
        skip=skip,
        skip_reason=skip_reason,
        rationale=rationale,
        argument_source="llm",
    )


class OpenAICompatibleStepArgumentPlanner:
    def __init__(
        self,
        config: LlmReportConfig,
        *,
        client: OpenAICompatibleReportClient | None = None,
    ) -> None:
        self.config = config
        self._client = client or OpenAICompatibleReportClient(config)

    @classmethod
    def from_settings(
        cls,
        settings: RootSeekerSettings | None = None,
    ) -> OpenAICompatibleStepArgumentPlanner | None:
        settings = settings or RootSeekerSettings()
        if not settings.skill_llm_argument_planning_enabled:
            return None
        config = LlmReportConfig.from_settings(settings)
        if config is None:
            return None
        return cls(config)

    def plan(
        self,
        *,
        case_request: CaseCreateRequest,
        action: str,
        tool_spec: ToolSpec,
        skill_context: SkillStepContext,
        step_outputs: dict[str, dict[str, Any]],
        report_summary: dict[str, Any] | None = None,
    ) -> StepArgumentPlan | None:
        messages = build_step_argument_messages(
            case_request=case_request,
            action=action,
            tool_spec=tool_spec,
            skill_context=skill_context,
            step_outputs=step_outputs,
            report_summary=report_summary,
        )
        result = self._client.complete(messages)
        if not result.ok:
            return None
        return parse_step_argument_content(result.content)


LlmStepArgumentPlanner = OpenAICompatibleStepArgumentPlanner


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


def _first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return ""
