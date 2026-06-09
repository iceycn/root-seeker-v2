from __future__ import annotations

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.infra_core import RootSeekerSettings

from .result import ModelRoute

__all__ = ["ModelRouter"]


class ModelRouter:
    """Choose the attempt execution route and expose why that route was selected."""

    def __init__(self, settings: RootSeekerSettings | None = None) -> None:
        self._settings = settings or RootSeekerSettings()

    def select_route(self, case_request: CaseCreateRequest) -> ModelRoute:
        configured = bool(
            self._settings.llm_enabled
            and self._settings.llm_base_url
            and self._settings.llm_api_key
            and self._settings.llm_model
        )
        if configured and self._settings.agent_llm_tool_planning_enabled:
            return ModelRoute(
                mode="llm_tool_plan",
                provider_name=self._settings.llm_provider_name,
                model=self._settings.llm_model,
                reason="LLM tool planning is configured; model will propose MCP tool calls.",
                metadata={
                    "service_name": case_request.service_name,
                    "max_tool_calls": self._settings.agent_llm_max_tool_calls,
                    "allow_write_tools": self._settings.agent_llm_allow_write_tools,
                },
            )
        if configured:
            return ModelRoute(
                mode="llm_report_enhanced_flow",
                provider_name=self._settings.llm_provider_name,
                model=self._settings.llm_model,
                reason="LLM report enhancement is configured; default flow evidence will be summarized by the model.",
                metadata={"service_name": case_request.service_name},
            )
        return ModelRoute(
            mode="rule_flow",
            provider_name=None,
            model=None,
            reason="LLM settings are incomplete or disabled; use deterministic rule flow.",
            metadata={"service_name": case_request.service_name},
        )
