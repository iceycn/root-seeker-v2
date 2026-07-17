from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from rootseeker.contracts.case import StepStatus
from rootseeker.contracts.tool import ToolCallRequest, ToolCallResult
from rootseeker.flow_runtime.flow_executor import FlowExecutionResult
from rootseeker.mcp_plane import McpGateway

from .result import ToolExecutionTrace

__all__ = ["ToolCallExecution", "ToolCallLoop"]


@dataclass(frozen=True)
class ToolCallExecution:
    request: ToolCallRequest
    result: ToolCallResult
    trace: ToolExecutionTrace


@dataclass
class ToolCallLoop:
    gateway: McpGateway | None = None
    max_content_chars: int = 800
    max_concurrency: int = 1

    def execute(
        self,
        requests: list[ToolCallRequest],
        *,
        plugin_id: str | None = None,
        actor: str = "agent-runtime",
        plan_metadata_by_step_id: dict[str, dict[str, Any]] | None = None,
    ) -> list[ToolExecutionTrace]:
        return [
            record.trace
            for record in self.execute_records(
                requests,
                plugin_id=plugin_id,
                actor=actor,
                plan_metadata_by_step_id=plan_metadata_by_step_id,
            )
        ]

    def execute_records(
        self,
        requests: list[ToolCallRequest],
        *,
        plugin_id: str | None = None,
        actor: str = "agent-runtime",
        plan_metadata_by_step_id: dict[str, dict[str, Any]] | None = None,
    ) -> list[ToolCallExecution]:
        if self.gateway is None:
            raise ValueError("gateway is required to execute tool calls")
        if self.max_concurrency > 1 and len(requests) > 1:
            return self._execute_records_concurrently(
                requests,
                plugin_id=plugin_id,
                actor=actor,
                plan_metadata_by_step_id=plan_metadata_by_step_id,
            )
        records: list[ToolCallExecution] = []
        for request in requests:
            result = self.gateway.invoke(request, plugin_id=plugin_id, actor=actor)
            trace = self.trace_from_result(
                step_id=request.step_id,
                result=result,
                plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id),
            )
            records.append(ToolCallExecution(request=request, result=result, trace=trace))
        return records

    def _execute_records_concurrently(
        self,
        requests: list[ToolCallRequest],
        *,
        plugin_id: str | None,
        actor: str,
        plan_metadata_by_step_id: dict[str, dict[str, Any]] | None,
    ) -> list[ToolCallExecution]:
        worker_count = min(max(1, self.max_concurrency), len(requests))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(
                    lambda request: self.gateway.invoke(request, plugin_id=plugin_id, actor=actor),
                    requests,
                )
            )
        return [
            ToolCallExecution(
                request=request,
                result=result,
                trace=self.trace_from_result(
                    step_id=request.step_id,
                    result=result,
                    plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id),
                ),
            )
            for request, result in zip(requests, results, strict=True)
        ]

    def from_flow_result(self, result: FlowExecutionResult) -> list[ToolExecutionTrace]:
        traces: list[ToolExecutionTrace] = []
        for step in result.trace.steps:
            if not step.tool_name:
                continue
            content = result.step_outputs.get(step.step_id)
            if content is None:
                content = dict(step.detail.get("outputs", {}))
            traces.append(
                ToolExecutionTrace(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    ok=step.status == StepStatus.COMPLETED,
                    latency_ms=0,
                    content_preview=self._preview(content),
                    error_code=step.error.code if step.error is not None else None,
                    error_message=step.error.message if step.error is not None else None,
                )
            )
        return traces

    def trace_from_result(
        self,
        *,
        step_id: str,
        result: ToolCallResult,
        plan_metadata: dict[str, Any] | None = None,
    ) -> ToolExecutionTrace:
        return ToolExecutionTrace(
            step_id=step_id,
            tool_name=result.tool_name,
            ok=result.ok,
            latency_ms=result.latency_ms,
            content_preview=self._preview(result.content),
            error_code=result.error.code if result.error is not None else None,
            error_message=result.error.message if result.error is not None else None,
            plan_metadata={
                key: value for key, value in dict(plan_metadata or {}).items() if value is not None
            },
        )

    def _preview(self, content: dict) -> dict:
        raw = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
        if len(raw) <= self.max_content_chars:
            return dict(content)
        return {"_truncated": True, "preview": raw[: self.max_content_chars]}
