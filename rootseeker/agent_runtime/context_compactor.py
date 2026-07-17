from __future__ import annotations

import json

from .result import CompactedContext, ToolExecutionTrace

__all__ = ["ContextCompactor"]


class ContextCompactor:
    def __init__(self, *, max_tool_traces: int = 6, max_content_chars: int = 2400) -> None:
        self.max_tool_traces = max_tool_traces
        self.max_content_chars = max_content_chars

    def compact(
        self,
        *,
        prompt_messages: list[dict[str, str]],
        tool_traces: list[ToolExecutionTrace],
    ) -> CompactedContext:
        source_size = _serialized_size(prompt_messages, tool_traces)
        token_estimate = max(1, source_size // 4) if source_size else 0
        should_compact = (
            len(tool_traces) > self.max_tool_traces or source_size > self.max_content_chars
        )
        if not should_compact:
            return CompactedContext(
                compacted=False,
                summary="Context is within budget; no compaction needed.",
                retained_step_ids=[trace.step_id for trace in tool_traces],
                omitted_step_ids=[],
                source_token_estimate=token_estimate,
            )

        failed = [trace.step_id for trace in tool_traces if not trace.ok]
        recent = [trace.step_id for trace in tool_traces[-self.max_tool_traces :]]
        retained = _dedupe(failed + recent)
        omitted = [trace.step_id for trace in tool_traces if trace.step_id not in retained]
        failed_count = len(failed)
        summary = (
            f"Compacted {len(tool_traces)} tool traces into {len(retained)} retained steps; "
            f"omitted {len(omitted)} earlier low-priority steps; failed_steps={failed_count}."
        )
        return CompactedContext(
            compacted=True,
            summary=summary,
            retained_step_ids=retained,
            omitted_step_ids=omitted,
            source_token_estimate=token_estimate,
        )


def _serialized_size(
    prompt_messages: list[dict[str, str]], tool_traces: list[ToolExecutionTrace]
) -> int:
    payload = {
        "messages": prompt_messages,
        "tool_traces": [
            {
                "step_id": trace.step_id,
                "tool_name": trace.tool_name,
                "ok": trace.ok,
                "content_preview": trace.content_preview,
                "error_code": trace.error_code,
                "error_message": trace.error_message,
                "plan_metadata": trace.plan_metadata,
            }
            for trace in tool_traces
        ],
    }
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
