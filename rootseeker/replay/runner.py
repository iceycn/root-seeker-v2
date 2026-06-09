from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plugins.builtin.default_log_triage_flow import DEFAULT_FLOW_PLUGIN_ID, DefaultFlowRunResult
from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.common import new_id
from rootseeker.contracts.execution_trace import CaseExecutionTrace, SkillExecutionTrace
from rootseeker.contracts.replay import ReplayCaseSpec, ReplayRunSnapshot
from rootseeker.evaluation.metrics import aggregate_suite_metrics, evaluate_run_metrics
from rootseeker.evaluation.quality_gate import (
    QualityGatePolicy,
    QualityGateResult,
    evaluate_quality_gate,
)
from rootseeker.evaluation.reporting import EvaluationReport, build_evaluation_report
from rootseeker.replay.store import ReplayStore

__all__ = ["ReplayRunner", "ReplaySuiteResult"]


@dataclass
class ReplaySuiteResult:
    report: EvaluationReport
    traces: list[CaseExecutionTrace]
    snapshots: list[ReplayRunSnapshot]


class ReplayRunner:
    def __init__(
        self,
        runtime: DevRuntime,
        store: ReplayStore,
        *,
        gate_policy: QualityGatePolicy | None = None,
    ) -> None:
        self._runtime = runtime
        self._store = store
        self._gate_policy = gate_policy

    def load_cases(self, cases: list[ReplayCaseSpec]) -> None:
        for case in cases:
            self._store.upsert_case(case)

    def run_suite(self, *, suite_name: str, repeat_each: int = 1) -> ReplaySuiteResult:
        if repeat_each < 1:
            raise ValueError("repeat_each must be >= 1")
        cases = self._store.list_cases()
        traces: list[CaseExecutionTrace] = []
        snapshots: list[ReplayRunSnapshot] = []
        metrics_list: list[dict[str, float]] = []
        case_summaries: list[dict[str, Any]] = []

        for case in cases:
            run_metrics: list[dict[str, float]] = []
            run_ids: list[str] = []
            for _ in range(repeat_each):
                run_id = new_id("replay-run-")
                run = self._runtime.run_default_flow_from_payload(case.alert_payload)
                m = evaluate_run_metrics(case, run)
                run_metrics.append(m)
                metrics_list.append(m)
                trace = _to_case_execution_trace(run, run_id=run_id)
                traces.append(trace)
                snap = ReplayRunSnapshot(
                    replay_id=case.replay_id,
                    run_id=run_id,
                    case_id=run.case.case_id,
                    skill_name=run.case.selected_skills[0] if run.case.selected_skills else "unknown",
                    flow_plugin_id=DEFAULT_FLOW_PLUGIN_ID,
                    passed=run.case.status.value == "completed",
                    metrics=m,
                    errors=[r.error.message for r in run.tool_results if r.error is not None],
                )
                snapshots.append(snap)
                self._store.add_run(snap)
                run_ids.append(run_id)

            avg_case_metrics = aggregate_suite_metrics(run_metrics)
            case_summaries.append(
                {
                    "replay_id": case.replay_id,
                    "name": case.name,
                    "runs": len(run_ids),
                    "metrics": avg_case_metrics,
                    "run_ids": run_ids,
                }
            )

        aggregate = aggregate_suite_metrics(metrics_list)
        gate: QualityGateResult = evaluate_quality_gate(aggregate, policy=self._gate_policy)
        report = build_evaluation_report(
            report_id=new_id("eval-"),
            suite_name=suite_name,
            case_count=len(cases),
            aggregate_metrics=aggregate,
            gate_result=gate,
            case_summaries=case_summaries,
        )
        return ReplaySuiteResult(report=report, traces=traces, snapshots=snapshots)


def _to_case_execution_trace(run: DefaultFlowRunResult, *, run_id: str) -> CaseExecutionTrace:
    step_traces = [
        SkillExecutionTrace(
            skill_name=step.skill_name,
            skill_version="1.0.0",
            step_name=step.name,
            tool_calls=[step.action],
            inputs=step.inputs,
            outputs=step.outputs,
            errors=[] if step.status.value != "failed" else ["step failed"],
        )
        for step in run.case.steps
    ]
    return CaseExecutionTrace(
        case_id=run.case.case_id,
        skill_name=run.case.selected_skills[0] if run.case.selected_skills else "unknown",
        flow_plugin_id=DEFAULT_FLOW_PLUGIN_ID,
        step_traces=step_traces,
        mcp_call_ids=[f"{run_id}:{r.tool_name}" for r in run.tool_results],
        evidence_ids=[item.item_id for item in run.evidence_pack.items],
        report_id=run.report.case_id,
    )
