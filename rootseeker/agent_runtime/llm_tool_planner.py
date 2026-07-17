from __future__ import annotations

import json
from typing import Protocol

from rootseeker.analysis.llm_report import LlmReportConfig, OpenAICompatibleReportClient
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.tool import ToolPermissionLevel, ToolSpec
from rootseeker.infra_core import RootSeekerSettings

from .tool_plan import ToolPlanResult, parse_tool_plan_content

__all__ = ["LlmToolPlanner", "OpenAICompatibleToolPlanner", "build_tool_planner_messages"]


class LlmToolPlanner(Protocol):
    def plan(
        self,
        *,
        case_request: CaseCreateRequest,
        tools: list[ToolSpec],
        history_summary: str | None = None,
    ) -> ToolPlanResult: ...


class OpenAICompatibleToolPlanner:
    def __init__(
        self,
        config: LlmReportConfig,
        *,
        max_tool_calls: int,
        allow_write_tools: bool = False,
        client: OpenAICompatibleReportClient | None = None,
    ) -> None:
        self.config = config
        self.max_tool_calls = max_tool_calls
        self.allow_write_tools = allow_write_tools
        self._client = client or OpenAICompatibleReportClient(config)

    @classmethod
    def from_settings(
        cls,
        settings: RootSeekerSettings | None = None,
    ) -> OpenAICompatibleToolPlanner | None:
        settings = settings or RootSeekerSettings()
        if not settings.agent_llm_tool_planning_enabled:
            return None
        config = LlmReportConfig.from_settings(settings)
        if config is None:
            return None
        return cls(
            config,
            max_tool_calls=settings.agent_llm_max_tool_calls,
            allow_write_tools=settings.agent_llm_allow_write_tools,
        )

    def plan(
        self,
        *,
        case_request: CaseCreateRequest,
        tools: list[ToolSpec],
        history_summary: str | None = None,
    ) -> ToolPlanResult:
        allowed_tools = _allowed_tools(tools, allow_write_tools=self.allow_write_tools)
        messages = build_tool_planner_messages(
            case_request=case_request,
            tools=allowed_tools,
            max_tool_calls=self.max_tool_calls,
            history_summary=history_summary,
        )
        result = self._client.complete(messages)
        if not result.ok:
            return ToolPlanResult(
                ok=False,
                provider=result.provider,
                model=result.model,
                elapsed_ms=result.elapsed_ms,
                raw_content=result.content,
                error=result.error or result.reason or "llm planner failed",
            )
        allowed_names = {tool.name for tool in allowed_tools}
        plan = parse_tool_plan_content(
            result.content,
            allowed_tools=allowed_names,
            max_tool_calls=self.max_tool_calls,
            case_request=case_request,
        )
        if plan is None:
            return ToolPlanResult(
                ok=False,
                provider=result.provider,
                model=result.model,
                elapsed_ms=result.elapsed_ms,
                raw_content=result.content,
                error="llm planner returned no valid tool calls",
            )
        return ToolPlanResult(
            ok=True,
            plan=plan,
            provider=result.provider,
            model=result.model,
            elapsed_ms=result.elapsed_ms,
            raw_content=result.content,
        )


def build_tool_planner_messages(
    *,
    case_request: CaseCreateRequest,
    tools: list[ToolSpec],
    max_tool_calls: int,
    history_summary: str | None = None,
) -> list[dict[str, str]]:
    payload = {
        "case": case_request.model_dump(mode="json"),
        "max_tool_calls": max_tool_calls,
        "available_tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "permission_level": tool.permission_level.value,
                "tags": tool.tags,
            }
            for tool in tools
        ],
        "output_schema": {
            "rationale": "string",
            "tool_calls": [
                {
                    "step_id": "short stable id",
                    "tool_name": "one of available_tools.name",
                    "arguments": "JSON object; omit fields if defaults from case are enough",
                    "depends_on": "optional array of earlier step_id values",
                    "timeout_seconds": "optional positive number",
                    "required": "optional boolean; false means non-critical evidence",
                    "rationale": "why this call is needed",
                }
            ],
            "final_answer": "optional string",
        },
    }
    if history_summary:
        payload["prior_attempt_feedback"] = history_summary
    return [
        {
            "role": "system",
            "content": (
                "你是 RootSeeker Agent 工具规划器。只能输出紧凑 JSON，不要 Markdown。"
                "只能选择 available_tools 中的工具；执行会由系统通过 MCP Gateway 完成。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _allowed_tools(tools: list[ToolSpec], *, allow_write_tools: bool) -> list[ToolSpec]:
    if allow_write_tools:
        return list(tools)
    return [tool for tool in tools if tool.permission_level == ToolPermissionLevel.READ]
