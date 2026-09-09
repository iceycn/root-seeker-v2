"""Notify message variable catalog and context builder."""

from __future__ import annotations

import re

from rootseeker.analysis.call_chain import extract_exception_summary
from rootseeker.analysis.service_identity import is_placeholder_service_name, resolve_service_name
from rootseeker.channel_routing.message_template_render import render_message_template
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.report import CaseReport

__all__ = [
    "NOTIFY_VARIABLES",
    "SYSTEM_DEFAULT_TEMPLATE_BODY",
    "SYSTEM_TEMPLATE_ID",
    "build_notify_context",
    "render_notify_message",
]

SYSTEM_TEMPLATE_ID = "system-default"

NOTIFY_VARIABLES: list[dict[str, str]] = [
    {"name": "headline", "description": "通知标题（异常摘要 / 结论 / Case 标题）"},
    {"name": "problem", "description": "问题摘要"},
    {"name": "service", "description": "解析后的服务名"},
    {"name": "cause", "description": "结论标题（清洗并去重后）"},
    {"name": "narrative", "description": "说明（过滤过程性文案）"},
    {"name": "confidence", "description": "置信度展示，如 62%"},
    {"name": "case_id", "description": "Case ID"},
    {"name": "title", "description": "Case 原始标题"},
    {"name": "exception", "description": "从症状提取的异常摘要"},
    {"name": "symptom", "description": "症状原文（截断）"},
]

SYSTEM_DEFAULT_TEMPLATE_BODY = (
    "【RootSeeker】{{headline}}\n"
    "{{#problem}}问题：{{problem}}\n{{/problem}}"
    "{{#service}}服务：{{service}}\n{{/service}}"
    "{{#cause}}结论：{{cause}}\n{{/cause}}"
    "{{#narrative}}说明：{{narrative}}\n{{/narrative}}"
    "{{#confidence}}置信度：{{confidence}}\n{{/confidence}}"
    "Case：{{case_id}}"
)

_GENERIC_CASE_TITLES = frozenset({"", "t", "错误排查请求", "error triage", "case"})
_INDEXER_TAIL_RE = re.compile(
    r"(?:\s*;\s*)+(?:zoekt|gitnexus|qdrant|catalog)"
    r"(?:\s*;\s*(?:zoekt|gitnexus|qdrant|catalog))*\s*$",
    re.IGNORECASE,
)
_LOG_ERROR_PREFIX_RE = re.compile(r"^日志中发现错误:\s*")
_PROCEDURAL_NARRATIVE_RE = re.compile(r"共分析|分析已收敛|上下文片段")
_SYMPTOM_MAX = 500


def build_notify_context(*, case_request: CaseCreateRequest, report: CaseReport) -> dict[str, str]:
    from rootseeker.analysis.problem_summary import build_problem_summary

    exception = extract_exception_summary(case_request.symptom, max_chars=180)
    raw_cause = _clean_cause_title(
        report.root_cause.title if report.root_cause is not None else "",
        exception=exception,
    )
    headline = exception or raw_cause or _usable_case_title(case_request.title) or "排查完成"
    service = resolve_service_name(
        case_request.service_name,
        text=case_request.symptom,
        default="",
    )
    if is_placeholder_service_name(service):
        service = ""

    report_summary = str(report.summary or "").strip()
    problem = str((report.metadata or {}).get("problem_summary") or "").strip()
    if not problem and report_summary and not report_summary.startswith("Collected "):
        problem = report_summary
    if not problem:
        problem = build_problem_summary(
            symptom=case_request.symptom,
            service_name=service,
            exception=exception,
        )
    if not _should_include_problem_summary(problem, headline=headline):
        problem = ""

    cause = raw_cause
    if not (
        cause
        and cause not in headline
        and headline not in cause
        and cause not in problem
        and problem not in cause
    ):
        cause = ""

    narrative = ""
    if report.root_cause is not None:
        narrative = str(report.root_cause.narrative or "").strip()
    if not (
        narrative
        and narrative not in headline
        and narrative not in (raw_cause or "")
        and narrative not in problem
        and not _PROCEDURAL_NARRATIVE_RE.search(narrative)
    ):
        narrative = ""
    elif len(narrative) > 280:
        narrative = narrative[:277] + "..."

    confidence_value = report.root_cause.confidence if report.root_cause is not None else 0.0
    confidence = f"{int(round(confidence_value * 100))}%" if confidence_value > 0 else ""

    symptom = str(case_request.symptom or "")
    if len(symptom) > _SYMPTOM_MAX:
        symptom = symptom[:_SYMPTOM_MAX]

    return {
        "headline": headline,
        "problem": problem,
        "service": service,
        "cause": cause,
        "narrative": narrative,
        "confidence": confidence,
        "case_id": str(report.case_id),
        "title": str(case_request.title or ""),
        "exception": exception or "",
        "symptom": symptom,
    }


def render_notify_message(
    *,
    case_request: CaseCreateRequest,
    report: CaseReport,
    body: str | None = None,
) -> str:
    context = build_notify_context(case_request=case_request, report=report)
    return render_message_template(body or SYSTEM_DEFAULT_TEMPLATE_BODY, context)


def _should_include_problem_summary(problem: str, *, headline: str) -> bool:
    text = problem.strip()
    head = headline.strip()
    if not text:
        return False
    if text == head:
        return False
    if text == f"抛出 {head}":
        return False
    return True


def _usable_case_title(title: str) -> str:
    text = str(title or "").strip()
    if text.lower() in _GENERIC_CASE_TITLES or text in _GENERIC_CASE_TITLES:
        return ""
    return text


def _clean_cause_title(title: str, *, exception: str = "") -> str:
    text = _INDEXER_TAIL_RE.sub("", str(title or "").strip()).strip(" ;")
    text = _LOG_ERROR_PREFIX_RE.sub("", text).strip()
    if not text:
        return ""
    if exception and (text == exception or exception.startswith(text) or text.startswith(exception)):
        return ""
    return text
