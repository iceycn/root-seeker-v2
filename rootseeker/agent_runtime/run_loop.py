from __future__ import annotations

from collections.abc import Iterator

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.infra_core.agent_events import build_agent_event
from rootseeker.infra_core.settings import RootSeekerSettings

from .attempt_runner import AttemptRunner
from .result import AgentRunEvent, AgentRunResult, AttemptResult

__all__ = ["AgentRunLoop"]


class AgentRunLoop:
    def __init__(
        self,
        runtime: DevRuntime,
        *,
        flow_runtime: FlowRuntime | None = None,
        attempt_runner: AttemptRunner | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.runtime = runtime
        self.flow_runtime = flow_runtime or FlowRuntime(runtime)
        self.attempt_runner = attempt_runner or AttemptRunner(self.flow_runtime)
        configured_attempts = RootSeekerSettings().agent_max_attempts
        self.max_attempts = max(
            1, max_attempts if max_attempts is not None else configured_attempts
        )

    def run(self, case_request: CaseCreateRequest) -> AgentRunResult:
        final_result: AgentRunResult | None = None
        for event in self.run_stream(case_request):
            if event.result is not None:
                final_result = event.result
        if final_result is None:
            raise RuntimeError("agent run stream ended without result")
        return final_result

    def run_stream(self, case_request: CaseCreateRequest) -> Iterator[AgentRunEvent]:
        yield self._emit(
            action="agent.run.started",
            target="agent-runtime",
            detail={
                "title": case_request.title,
                "service_name": case_request.service_name,
                "source": case_request.source,
            },
        )
        attempts: list[AttemptResult] = []
        for idx in range(self.max_attempts):
            is_last_attempt = idx == self.max_attempts - 1
            attempt = self.attempt_runner.run_once(
                case_request,
                prior_attempts=attempts,
                allow_default_fallback=is_last_attempt,
            )
            attempts.append(attempt)
            yield from self._emit_attempt_events(attempt)
            if attempt.status == "completed":
                break
            if not is_last_attempt:
                yield self._emit(
                    action="agent.attempt.retrying",
                    target=attempt.case_id,
                    detail={
                        "case_id": attempt.case_id,
                        "attempt_id": attempt.attempt_id,
                        "next_attempt": idx + 2,
                        "max_attempts": self.max_attempts,
                    },
                )

        if not attempts:
            raise RuntimeError("agent run loop ended without attempts")

        final_attempt = attempts[-1]
        result = AgentRunResult(
            case_id=final_attempt.case_id,
            status=final_attempt.status,
            attempts=attempts,
            trace_id=final_attempt.flow_run_id,
            compacted_context=final_attempt.compacted_context,
            metadata={
                "max_attempts": self.max_attempts,
                "attempt_count": len(attempts),
                "route_mode": final_attempt.route.mode,
            },
        )
        yield self._emit(
            action=f"agent.run.{result.status}",
            target=result.case_id,
            detail={
                "case_id": result.case_id,
                "trace_id": result.trace_id,
                "attempt_count": len(result.attempts),
            },
            result=result,
        )

    def _emit_attempt_events(self, attempt: AttemptResult) -> Iterator[AgentRunEvent]:
        yield self._emit(
            action=f"agent.attempt.{attempt.status}",
            target=attempt.case_id,
            detail={
                "case_id": attempt.case_id,
                "attempt_id": attempt.attempt_id,
                "flow_run_id": attempt.flow_run_id,
                "route_mode": attempt.route.mode,
                "tool_trace_count": len(attempt.tool_traces),
            },
        )
        for trace in attempt.tool_traces:
            action = "agent.tool.trace" if trace.ok else "agent.tool.error"
            yield self._emit(
                action=action,
                target=attempt.case_id,
                detail={
                    "case_id": attempt.case_id,
                    "attempt_id": attempt.attempt_id,
                    "step_id": trace.step_id,
                    "tool_name": trace.tool_name,
                    "ok": trace.ok,
                    "error_code": trace.error_code,
                },
            )
        if attempt.compacted_context is not None and attempt.compacted_context.compacted:
            yield self._emit(
                action="agent.context.compacted",
                target=attempt.case_id,
                detail={
                    "case_id": attempt.case_id,
                    "attempt_id": attempt.attempt_id,
                    "retained_step_ids": attempt.compacted_context.retained_step_ids,
                    "omitted_step_ids": attempt.compacted_context.omitted_step_ids,
                    "source_token_estimate": attempt.compacted_context.source_token_estimate,
                },
            )

    def _emit(
        self,
        *,
        action: str,
        target: str,
        detail: dict,
        result: AgentRunResult | None = None,
    ) -> AgentRunEvent:
        audit_event = build_agent_event(
            action=action,
            actor="agent-runtime",
            target=target,
            detail=detail,
        )
        self.runtime.audit_log.append(audit_event)
        return AgentRunEvent(
            event_type=action,
            case_id=str(detail.get("case_id")) if detail.get("case_id") else None,
            attempt_id=str(detail.get("attempt_id")) if detail.get("attempt_id") else None,
            payload=dict(detail),
            result=result,
        )
