"""Tests for notify variable context and default template render."""

from __future__ import annotations

from rootseeker.channel_routing.notify_variables import (
    SYSTEM_DEFAULT_TEMPLATE_BODY,
    build_notify_context,
    render_notify_message,
)
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.evidence import RootCauseConclusion
from rootseeker.contracts.report import CaseReport


def test_build_notify_context_exposes_catalog_keys() -> None:
    ctx = build_notify_context(
        case_request=CaseCreateRequest(
            title="错误排查请求",
            symptom="java.lang.NullPointerException: boom\n\tat com.x.A.run(A.java:1)\n",
            service_name="demo-api",
            source="admin-error-chat",
        ),
        report=CaseReport(
            case_id="case-1",
            title="t",
            summary="s",
            evidence_item_ids=[],
            root_cause=RootCauseConclusion(
                title="NullPointerException",
                narrative="空指针",
                confidence=0.5,
            ),
        ),
    )
    for key in (
        "headline",
        "problem",
        "service",
        "cause",
        "narrative",
        "confidence",
        "case_id",
        "title",
        "exception",
        "symptom",
    ):
        assert key in ctx
    assert ctx["case_id"] == "case-1"
    assert ctx["confidence"] == "50%"


def test_default_template_includes_brand_and_case() -> None:
    msg = render_notify_message(
        case_request=CaseCreateRequest(
            title="错误排查请求",
            symptom="java.lang.IllegalStateException: boom\n\tat com.example.A.run(A.java:1)\n",
            service_name="demo-api",
            source="admin-error-chat",
        ),
        report=CaseReport(case_id="case-proc", title="t", summary="s", evidence_item_ids=[]),
        body=SYSTEM_DEFAULT_TEMPLATE_BODY,
    )
    assert "【RootSeeker】" in msg
    assert "case-proc" in msg
