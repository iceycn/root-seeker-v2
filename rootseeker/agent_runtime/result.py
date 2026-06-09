from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AgentRunEvent",
    "AgentRunResult",
    "AttemptResult",
    "CompactedContext",
    "ModelRoute",
    "ToolExecutionTrace",
]


@dataclass(frozen=True)
class ModelRoute:
    mode: str
    provider_name: str | None = None
    model: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExecutionTrace:
    step_id: str
    tool_name: str
    ok: bool
    latency_ms: int = 0
    content_preview: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    plan_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompactedContext:
    compacted: bool
    summary: str
    retained_step_ids: list[str] = field(default_factory=list)
    omitted_step_ids: list[str] = field(default_factory=list)
    source_token_estimate: int = 0


@dataclass(frozen=True)
class AttemptResult:
    attempt_id: str
    case_id: str
    status: str
    prompt_messages: list[dict[str, str]]
    route: ModelRoute
    tool_traces: list[ToolExecutionTrace] = field(default_factory=list)
    compacted_context: CompactedContext | None = None
    flow_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunResult:
    case_id: str
    status: str
    attempts: list[AttemptResult] = field(default_factory=list)
    trace_id: str | None = None
    compacted_context: CompactedContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunEvent:
    event_type: str
    case_id: str | None = None
    attempt_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: AgentRunResult | None = None
