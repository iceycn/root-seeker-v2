from __future__ import annotations

from .result import AttemptResult

__all__ = ["build_attempt_history_summary"]


def build_attempt_history_summary(attempts: list[AttemptResult], *, limit: int = 3) -> str | None:
    if not attempts:
        return None
    lines: list[str] = []
    for idx, attempt in enumerate(attempts[-limit:], start=max(1, len(attempts) - limit + 1)):
        failed_tools = [
            f"{trace.tool_name}:{trace.error_code or 'failed'}"
            for trace in attempt.tool_traces
            if not trace.ok
        ]
        tool_plan = attempt.metadata.get("tool_plan")
        planner_error = ""
        if isinstance(tool_plan, dict) and isinstance(tool_plan.get("error"), str):
            planner_error = tool_plan["error"]
        fragments = [
            f"attempt={idx}",
            f"status={attempt.status}",
            f"route={attempt.route.mode}",
        ]
        if failed_tools:
            fragments.append(f"failed_tools={','.join(failed_tools)}")
        if planner_error:
            fragments.append(f"planner_error={planner_error}")
        lines.append("; ".join(fragments))
    return "\n".join(lines)
