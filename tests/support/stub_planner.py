from __future__ import annotations

from rootseeker.agent_runtime.tool_plan import ToolPlan, ToolPlanCall, ToolPlanResult
from rootseeker.contracts.case import CaseCreateRequest

__all__ = ["IncidentNormalizePlanner"]


class IncidentNormalizePlanner:
    """Test planner that returns a single allowed playbook tool call."""

    def plan(
        self,
        *,
        case_request: CaseCreateRequest,
        tools,
        history_summary=None,
        **kwargs,
    ) -> ToolPlanResult:
        del tools, history_summary, kwargs
        return ToolPlanResult(
            ok=True,
            provider="stub",
            model="stub-planner",
            plan=ToolPlan(
                rationale="stub one incident.normalize call",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="incident.normalize",
                        step_id="normalize-incident",
                        arguments={
                            "payload": {
                                "title": case_request.title,
                                "message": case_request.symptom,
                                "service_name": case_request.service_name,
                                "source": case_request.source,
                                **dict(case_request.metadata),
                            }
                        },
                    )
                ],
            ),
        )
