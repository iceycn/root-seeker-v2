from __future__ import annotations

from rootseeker.analysis.llm_report import (
    LlmReportConfig,
    LlmReportResult,
    OpenAICompatibleReportClient,
    apply_llm_report_result,
)
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
) -> CaseReport:
    analyzer = engine or RootCauseEngine()
    context = build_context_window(pack)
    analysis = analyzer.analyze(pack=pack, context=context)
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
    client, skip_reason = (llm_client, "") if llm_client is not None else _build_default_llm_client(settings)
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
