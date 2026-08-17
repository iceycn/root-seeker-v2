from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from rootseeker.analysis.convergence_checker import ConvergenceStatus
from rootseeker.analysis.evidence_expander import McpGatewayEvidenceExpander
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, EvidenceType
from rootseeker.contracts.tool import ToolCallResult
from rootseeker.storage.mysql_conn import MysqlConnectConfig
from rootseeker.storage.mysql_replay_history import MysqlReplayHistoryStore


def test_mcp_gateway_evidence_expander_fetches_logs_when_missing() -> None:
    class _Gateway:
        def invoke(self, request, *, actor: str) -> ToolCallResult:
            assert request.tool_name == "log.query_by_trace_id"
            assert actor == "root_cause_engine"
            return ToolCallResult(
                ok=True,
                tool_name="log.query_by_trace_id",
                content={
                    "query_key": "trace:t1",
                    "records": [
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "message": "error timeout",
                            "level": "ERROR",
                            "trace_id": "t1",
                            "raw": {},
                        }
                    ],
                    "truncated": False,
                    "metadata": {},
                },
            )

    pack = EvidencePack(case_id="case-1", summary="pack")
    convergence = ConvergenceStatus(
        is_converged=False,
        confidence_threshold_met=False,
        sufficient_evidence=False,
        top_hypothesis_gap=0.0,
        recommendation="need more",
        iterations_remaining=2,
    )
    expander = McpGatewayEvidenceExpander(
        _Gateway(),
        case_id="case-1",
        trace_id="t1",
        service_name="order-service",
    )

    expanded = expander.expand(pack, iteration=1, convergence=convergence)

    assert len(expanded.items) == 1
    assert expanded.items[0].type == EvidenceType.LOG
    assert expanded.items[0].source == "log.query_by_trace_id"


def test_mcp_gateway_evidence_expander_skips_when_logs_present_and_sufficient() -> None:
    class _Gateway:
        def invoke(self, request, *, actor: str) -> ToolCallResult:
            raise AssertionError("should not invoke gateway")

    pack = EvidencePack(case_id="case-1", summary="pack")
    pack.items.append(
        EvidenceItem(
            item_id="ev-1",
            type=EvidenceType.LOG,
            source="log.query_by_trace_id",
            content={"message": "existing"},
        )
    )
    convergence = ConvergenceStatus(
        is_converged=False,
        confidence_threshold_met=True,
        sufficient_evidence=True,
        top_hypothesis_gap=0.3,
        recommendation="gap",
        iterations_remaining=1,
    )
    expander = McpGatewayEvidenceExpander(_Gateway(), case_id="case-1", trace_id="t1")

    expanded = expander.expand(pack, iteration=1, convergence=convergence)

    assert expanded is pack
    assert len(expanded.items) == 1
