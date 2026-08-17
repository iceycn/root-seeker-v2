from __future__ import annotations

from typing import Any

from rootseeker.analysis.llm_report import (
    LlmReportConfig,
    LlmReportResult,
    OpenAICompatibleReportClient,
    apply_llm_report_result,
)
from rootseeker.analysis.evidence_expander import EvidenceExpander, McpGatewayEvidenceExpander
from rootseeker.analysis.root_cause_engine import RootCauseEngine
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.report import CaseReport
from rootseeker.evidence import build_context_window
from rootseeker.infra_core.settings import RootSeekerSettings

__all__ = ["build_case_report"]


def build_case_report(
    *,
    case_id: str,
    title: str,
    pack: EvidencePack,
    engine: RootCauseEngine | None = None,
    llm_client: OpenAICompatibleReportClient | None = None,
    settings: RootSeekerSettings | None = None,
    gateway: Any | None = None,
    trace_id: str | None = None,
    service_name: str | None = None,
) -> CaseReport:
    active_settings = settings or RootSeekerSettings()
    analyzer = engine or RootCauseEngine()
    context = build_context_window(pack)
    evidence_expander: EvidenceExpander | None = None
    if gateway is not None and active_settings.root_cause_mcp_expansion_enabled:
        resolved_trace = trace_id or _trace_id_from_pack(pack)
        if resolved_trace:
            evidence_expander = McpGatewayEvidenceExpander(
                gateway,
                case_id=case_id,
                trace_id=resolved_trace,
                service_name=service_name,
            )
    analysis = analyzer.analyze(
        pack=pack,
        context=context,
        evidence_expander=evidence_expander,
    )
    evidence_ids = [item.item_id for item in pack.items]
    summary = (
        f"Collected {len(pack.items)} evidence item(s); "
        f"generated {len(analysis.hypotheses)} hypothesis(es)."
    )

    report = CaseReport(
        case_id=case_id,
        title=title,
        summary=summary,
        root_cause=analysis.conclusion,
        evidence_item_ids=evidence_ids,
        metadata={
            "builder": "root_cause_engine",
            "hypotheses": [hyp.model_dump(mode="json") for hyp in analysis.hypotheses],
            "context_used_tokens": context.used_tokens,
        },
    )
    client, skip_reason = (
        (llm_client, "") if llm_client is not None else _build_default_llm_client(settings)
    )
    if client is None:
        skipped = LlmReportResult(ok=False, skipped=True, reason=skip_reason or "not_configured")
        return apply_llm_report_result(report, skipped)
    llm_result = client.analyze_case(
        case_id=case_id,
        title=title,
        pack=pack,
        context=context,
        analysis=analysis,
    )
    return apply_llm_report_result(report, llm_result)


def _trace_id_from_pack(pack: EvidencePack) -> str | None:
    for item in pack.items:
        content = item.content or {}
        trace_id = content.get("trace_id") or content.get("metadata", {}).get("trace_id")
        if isinstance(trace_id, str) and trace_id.strip():
            return trace_id.strip()
    return None


def _build_default_llm_client(
    settings: RootSeekerSettings | None,
) -> tuple[OpenAICompatibleReportClient | None, str]:
    active_settings = settings or RootSeekerSettings()
    if not active_settings.llm_enabled:
        return None, "disabled"
    config = LlmReportConfig.from_settings(active_settings)
    if config is None:
        return None, "not_configured"
    return OpenAICompatibleReportClient(config), ""
