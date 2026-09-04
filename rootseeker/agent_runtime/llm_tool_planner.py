from __future__ import annotations

import json
from typing import Any, Protocol

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
        playbook_text: str = "",
        skill_catalog: list[dict[str, str]] | None = None,
        allowed_tool_names: set[str] | None = None,
        runtime_backends: dict[str, Any] | None = None,
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
        playbook_text: str = "",
        skill_catalog: list[dict[str, str]] | None = None,
        allowed_tool_names: set[str] | None = None,
        runtime_backends: dict[str, Any] | None = None,
    ) -> ToolPlanResult:
        allowed_tools = _allowed_tools(
            tools,
            allow_write_tools=self.allow_write_tools,
            allowed_tool_names=allowed_tool_names,
        )
        messages = build_tool_planner_messages(
            case_request=case_request,
            tools=allowed_tools,
            max_tool_calls=self.max_tool_calls,
            history_summary=history_summary,
            playbook_text=playbook_text,
            skill_catalog=skill_catalog,
            allowed_tool_names=allowed_tool_names,
            runtime_backends=runtime_backends,
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
        if allowed_tool_names is not None:
            allowed_names = {name for name in allowed_names if name in allowed_tool_names}
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
    playbook_text: str = "",
    skill_catalog: list[dict[str, str]] | None = None,
    allowed_tool_names: set[str] | None = None,
    runtime_backends: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    if allowed_tool_names is not None:
        tools = [tool for tool in tools if tool.name in allowed_tool_names]
    payload = {
        "case": case_request.model_dump(mode="json"),
        "max_tool_calls": max_tool_calls,
        "playbook": playbook_text,
        "skill_catalog": list(skill_catalog or []),
        "runtime_backends": dict(runtime_backends or {}),
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
    if allowed_tool_names is not None:
        payload["allowed_tool_names"] = sorted(allowed_tool_names)
    if history_summary:
        payload["prior_attempt_feedback"] = history_summary
    return [
        {
            "role": "system",
            "content": (
                "你是 RootSeeker Agent 工具规划器。只能输出紧凑 JSON，不要 Markdown。"
                "只能选择 available_tools 中的工具；执行会由系统通过 MCP Gateway 完成。"
                "runtime_backends.configured=false 的工具不要占用 max_tool_calls。"
                "若 available_tools 含 incident.normalize，必须作为第一步，"
                "code.find_callers 必须 depends_on 该步。"
                "code.read 的 path 必须是业务类文件，禁止 Spring/JDK 框架文件"
                "（如 AbstractFallbackSQLExceptionTranslator.java、Base64.java）。"
                "code.read 必须 depends_on incident.normalize，"
                "并用 methods 传入该文件在调用链上的方法名，不要读整文件。"
                "用堆栈里的包名定位仓库，不要默认当前服务名。"
                "notify.send 由系统在报告生成后根据通知渠道开关决定是否发送，不要放入 tool plan。"
                "未配置的 log/trace、catalog 不要用来填满配额。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _allowed_tools(
    tools: list[ToolSpec],
    *,
    allow_write_tools: bool,
    allowed_tool_names: set[str] | None = None,
) -> list[ToolSpec]:
    if allow_write_tools:
        return list(tools)
    return [
        tool
        for tool in tools
        if tool.permission_level == ToolPermissionLevel.READ
        or (allowed_tool_names is not None and tool.name in allowed_tool_names)
    ]
