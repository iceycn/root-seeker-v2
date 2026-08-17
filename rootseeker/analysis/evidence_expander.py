"""Optional evidence expansion for multi-iteration root cause analysis."""

from __future__ import annotations

from typing import Protocol

from rootseeker.analysis.convergence_checker import ConvergenceStatus
from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.contracts.log_query import LogQueryResult
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.evidence import append_log_query_evidence
from rootseeker.mcp_plane import McpGateway

__all__ = ["EvidenceExpander", "McpGatewayEvidenceExpander"]


class EvidenceExpander(Protocol):
    def expand(
        self,
        pack: EvidencePack,
        *,
        iteration: int,
        convergence: ConvergenceStatus,
    ) -> EvidencePack:
        """Return an evidence pack that may include newly fetched items."""


class McpGatewayEvidenceExpander:
    """Fetch supplemental MCP evidence when RCA iterations have not converged."""

    def __init__(
        self,
        gateway: McpGateway,
        *,
        case_id: str,
        trace_id: str | None = None,
        service_name: str | None = None,
        skill_name: str = "flows/default-log-triage",
    ) -> None:
        self._gateway = gateway
        self._case_id = case_id
        self._trace_id = trace_id
        self._service_name = service_name
        self._skill_name = skill_name
        self._fetched_tools: set[str] = set()

    def expand(
        self,
        pack: EvidencePack,
        *,
        iteration: int,
        convergence: ConvergenceStatus,
    ) -> EvidencePack:
        if convergence.is_converged or not self._trace_id:
            return pack
        if not self._should_fetch_logs(pack, convergence):
            return pack
        if "log.query_by_trace_id" in self._fetched_tools:
            return pack

        request = ToolCallRequest(
            case_id=self._case_id,
            step_id=f"rca-expand-{iteration}",
            skill_name=self._skill_name,
            tool_name="log.query_by_trace_id",
            arguments={
                "trace_id": self._trace_id,
                "service_name": self._service_name,
            },
        )
        result = self._gateway.invoke(request, actor="root_cause_engine")
        self._fetched_tools.add("log.query_by_trace_id")
        if not result.ok or not result.content:
            return pack

        expanded = pack.model_copy(deep=True)
        log_result = LogQueryResult.model_validate(result.content)
        append_log_query_evidence(
            expanded,
            tool_name="log.query_by_trace_id",
            result=log_result,
        )
        return expanded

    @staticmethod
    def _should_fetch_logs(pack: EvidencePack, convergence: ConvergenceStatus) -> bool:
        if convergence.is_converged:
            return False
        has_log = any(item.type == EvidenceType.LOG for item in pack.items)
        if not has_log:
            return True
        return not convergence.sufficient_evidence or not convergence.confidence_threshold_met
