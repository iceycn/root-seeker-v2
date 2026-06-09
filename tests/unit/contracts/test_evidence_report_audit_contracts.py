from rootseeker.contracts.audit import AuditCategory, AuditEvent
from rootseeker.contracts.evidence import (
    ContextWindow,
    EvidenceItem,
    EvidencePack,
    EvidenceType,
    Hypothesis,
    HypothesisStatus,
    RootCauseConclusion,
)
from rootseeker.contracts.report import CaseReport


def test_evidence_pack_and_context_window_are_separate() -> None:
    item = EvidenceItem(
        item_id="e1",
        type=EvidenceType.LOG,
        source="log.query_by_trace_id",
        content={"trace_id": "t1", "lines": ["a", "b"]},
    )
    pack = EvidencePack(case_id="case-1", items=[item], summary="two log lines")
    window = ContextWindow(
        case_id="case-1",
        max_tokens=8000,
        used_tokens=120,
        segments=["[log] trace t1: a, b"],
    )
    assert len(pack.items) == 1
    assert window.used_tokens <= window.max_tokens
    assert pack.summary
    assert window.segments


def test_hypothesis_and_root_cause_serialize() -> None:
    hyp = Hypothesis(
        hypothesis_id="h1",
        statement="timeout from downstream",
        status=HypothesisStatus.OPEN,
        evidence_item_ids=["e1"],
    )
    rc = RootCauseConclusion(
        title="Downstream latency",
        narrative="DB pool exhausted",
        confidence=0.72,
        contributing_factors=["spike in connections"],
    )
    report = CaseReport(
        case_id="case-1",
        title="Incident report",
        summary="RCA draft",
        root_cause=rc,
        evidence_item_ids=["e1"],
    )
    assert hyp.model_dump(mode="json")["status"] == "open"
    assert report.root_cause is not None
    assert report.root_cause.title == "Downstream latency"


def test_audit_event_covers_tool_and_state_shapes() -> None:
    tool_evt = AuditEvent(
        event_id="ae-1",
        category=AuditCategory.TOOL_CALL,
        action="mcp.invoke",
        actor="flow-runtime",
        target="log.query_by_trace_id",
        trace_id="trace-xyz",
        request_id="req-1",
        detail={"case_id": "c1", "latency_ms": 40},
    )
    state_evt = AuditEvent(
        event_id="ae-2",
        category=AuditCategory.STATE_CHANGE,
        action="case.transition",
        actor="supervisor",
        target="case-1",
        detail={"from": "pending", "to": "running"},
    )
    approval_evt = AuditEvent(
        event_id="ae-3",
        category=AuditCategory.APPROVAL,
        action="approval.grant",
        actor="user-42",
        target="step-9",
        detail={"step_id": "step-9"},
    )
    for evt in (tool_evt, state_evt, approval_evt):
        payload = evt.model_dump(mode="json")
        assert payload["actor"]
        assert payload["target"]
        assert payload["action"]
