from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from rootseeker.bootstrap import DevRuntime
from rootseeker.channel_routing import webhook_payload_to_case_create
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime import FlowRuntime

from .attempt_runner import AttemptRunner
from .llm_tool_planner import LlmToolPlanner
from .result import AgentRunEvent, AgentRunResult
from .run_loop import AgentRunLoop

__all__ = ["AgentRuntime"]


@dataclass
class AgentRuntime:
    runtime: DevRuntime
    flow_runtime: FlowRuntime
    run_loop: AgentRunLoop

    def __init__(
        self,
        runtime: DevRuntime,
        flow_runtime: FlowRuntime | None = None,
        run_loop: AgentRunLoop | None = None,
        *,
        tool_planner: LlmToolPlanner | None = None,
    ) -> None:
        self.runtime = runtime
        self.flow_runtime = flow_runtime or FlowRuntime(runtime)
        if run_loop is not None:
            self.run_loop = run_loop
            return
        planner = tool_planner if tool_planner is not None else getattr(runtime, "tool_planner", None)
        attempt_runner = (
            AttemptRunner(self.flow_runtime, tool_planner=planner)
            if planner is not None
            else AttemptRunner(self.flow_runtime)
        )
        self.run_loop = AgentRunLoop(
            runtime,
            flow_runtime=self.flow_runtime,
            attempt_runner=attempt_runner,
        )

    def run_case(self, case_request: CaseCreateRequest) -> str:
        return self.run_case_detailed(case_request).case_id

    def run_case_detailed(self, case_request: CaseCreateRequest) -> AgentRunResult:
        return self.run_loop.run(case_request)

    def run_case_stream(self, case_request: CaseCreateRequest) -> Iterator[AgentRunEvent]:
        yield from self.run_loop.run_stream(case_request)

    def run_payload(self, payload: dict[str, Any]) -> str:
        return self.run_payload_detailed(payload).case_id

    def run_payload_detailed(self, payload: dict[str, Any]) -> AgentRunResult:
        case_request = webhook_payload_to_case_create(payload)
        return self.run_case_detailed(case_request)

    def run_payload_stream(self, payload: dict[str, Any]) -> Iterator[AgentRunEvent]:
        case_request = webhook_payload_to_case_create(payload)
        yield from self.run_case_stream(case_request)
