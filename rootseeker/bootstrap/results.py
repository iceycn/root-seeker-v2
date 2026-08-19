from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rootseeker.contracts.case import CaseRecord
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.report import CaseReport
from rootseeker.contracts.tool import ToolCallResult

DEFAULT_FLOW_PLUGIN_ID = "builtin.default_log_triage_flow"

__all__ = ["DEFAULT_FLOW_PLUGIN_ID", "DefaultFlowRunResult"]


@dataclass
class DefaultFlowRunResult:
    case: CaseRecord
    evidence_pack: EvidencePack
    report: CaseReport
    tool_results: list[ToolCallResult]
    step_traces: list[dict[str, Any]] | None = None
