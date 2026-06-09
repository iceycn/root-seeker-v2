from datetime import UTC, datetime

from rootseeker.contracts.audit import AuditCategory, AuditEvent
from rootseeker.contracts.case import CaseRecord, CaseStatus
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, EvidenceType
from rootseeker.observability.audit import InMemoryAuditLog
from rootseeker.storage.memory import InMemoryCaseStore, InMemoryEvidenceStore


def test_case_store_put_get_list() -> None:
    store = InMemoryCaseStore()
    case = CaseRecord(
        case_id="c1",
        title="t",
        symptom="s",
        service_name="svc",
        source="webhook",
        status=CaseStatus.RUNNING,
    )
    store.put(case)
    got = store.get("c1")
    assert got is not None
    assert got.status == CaseStatus.RUNNING
    assert len(store.list_all()) == 1


def test_evidence_store_put_append() -> None:
    store = InMemoryEvidenceStore()
    i1 = EvidenceItem(
        item_id="e1",
        type=EvidenceType.LOG,
        source="log.query",
        content={"x": 1},
    )
    store.put_pack(EvidencePack(case_id="c1", items=[i1], summary="s"))
    i2 = EvidenceItem(
        item_id="e2",
        type=EvidenceType.TRACE,
        source="trace.get_chain",
        content={},
    )
    pack = store.append_items("c1", [i2])
    assert len(pack.items) == 2
    assert store.get_pack("c1") is pack


def test_audit_log_append_and_query_by_case() -> None:
    log = InMemoryAuditLog()
    log.append(
        AuditEvent(
            event_id="a1",
            category=AuditCategory.TOOL_CALL,
            action="mcp.invoke",
            actor="runtime",
            target="log.query",
            detail={"case_id": "c1"},
        )
    )
    log.append(
        AuditEvent(
            event_id="a2",
            category=AuditCategory.STATE_CHANGE,
            action="case.transition",
            actor="supervisor",
            target="c2",
            detail={"from": "pending", "to": "running"},
        )
    )
    log.append(
        AuditEvent(
            event_id="a3",
            category=AuditCategory.APPROVAL,
            action="approve",
            actor="u1",
            target="step-1",
            detail={"case_id": "c1"},
        )
    )
    c1_events = log.list_events(case_id="c1")
    assert len(c1_events) == 2
    assert log.count() == 3


def test_audit_log_limit_returns_tail() -> None:
    log = InMemoryAuditLog()
    base = datetime.now(UTC)
    for i in range(5):
        log.append(
            AuditEvent(
                event_id=f"id-{i}",
                category=AuditCategory.SYSTEM,
                action="tick",
                actor="cron",
                target="t",
                detail={"case_id": "c1", "i": i},
                occurred_at=base,
            )
        )
    tail = log.list_events(case_id="c1", limit=2)
    assert len(tail) == 2
    assert tail[-1].detail["i"] == 4
