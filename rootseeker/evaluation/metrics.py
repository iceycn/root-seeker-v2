from __future__ import annotations

import re
from statistics import mean

from plugins.builtin.default_log_triage_flow import DefaultFlowRunResult
from rootseeker.contracts.replay import ReplayCaseSpec

__all__ = ["evaluate_run_metrics", "aggregate_suite_metrics"]

_SENSITIVE_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(secret|token|password)\s*[:=]\s*[\w\-]{6,}"),
]


def evaluate_run_metrics(case: ReplayCaseSpec, run: DefaultFlowRunResult) -> dict[str, float]:
    step_actions = {s.action for s in run.case.steps}
    evidence_types = {item.type.value for item in run.evidence_pack.items}
    report_text = f"{run.report.title}\n{run.report.summary}"
    service_hit = 1.0 if run.case.service_name == case.case_request.service_name else 0.0
    trace_expected = str(case.case_request.metadata.get("trace_id", "")).strip()
    trace_hit = 1.0 if trace_expected and _trace_found(run, trace_expected) else 0.0
    log_hit = 1.0 if "log.query_by_trace_id" in step_actions else 0.0
    trace_chain_hit = 1.0 if "trace" in evidence_types else 0.0
    code_hit = 1.0 if "code.search" in step_actions or "code" in evidence_types else 0.0
    report_bullets_hit = _expected_bullet_hit(case.expected_report_bullets, report_text)
    tool_fail_rate = _tool_fail_rate(run)
    sensitive_leak_count = float(_sensitive_leaks(run))
    audit_completeness = 1.0 if run.tool_results else 0.0
    stability_hint = 1.0 if run.case.status.value == "completed" else 0.0

    return {
        "service_accuracy": service_hit,
        "trace_id_accuracy": trace_hit,
        "log_coverage": log_hit,
        "trace_coverage": trace_chain_hit,
        "code_coverage": code_hit,
        "report_bullet_coverage": report_bullets_hit,
        "tool_fail_rate": tool_fail_rate,
        "sensitive_leak_count": sensitive_leak_count,
        "audit_completeness": audit_completeness,
        "stability_score": stability_hint,
    }


def aggregate_suite_metrics(case_metrics: list[dict[str, float]]) -> dict[str, float]:
    if not case_metrics:
        return {}
    keys = sorted({k for m in case_metrics for k in m.keys()})
    return {k: mean(m.get(k, 0.0) for m in case_metrics) for k in keys}


def _expected_bullet_hit(expected: list[str], text: str) -> float:
    if not expected:
        return 1.0
    lower = text.lower()
    hits = sum(1 for token in expected if token.lower() in lower)
    return hits / len(expected)


def _tool_fail_rate(run: DefaultFlowRunResult) -> float:
    if not run.tool_results:
        return 1.0
    failures = sum(1 for r in run.tool_results if not r.ok)
    return failures / len(run.tool_results)


def _trace_found(run: DefaultFlowRunResult, trace_id: str) -> bool:
    for item in run.evidence_pack.items:
        text = str(item.content)
        if trace_id in text:
            return True
    return False


def _sensitive_leaks(run: DefaultFlowRunResult) -> int:
    corpus = [str(run.report.model_dump(mode="json")), str(run.evidence_pack.model_dump(mode="json"))]
    count = 0
    for text in corpus:
        for pattern in _SENSITIVE_PATTERNS:
            count += len(pattern.findall(text))
    return count
