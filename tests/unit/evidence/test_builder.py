from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.contracts.log_query import LogQueryResult, LogRecord
from rootseeker.evidence import append_log_query_evidence, append_tool_json_evidence


def test_append_log_query_evidence() -> None:
    pack = EvidencePack(case_id="c1")
    res = LogQueryResult(
        query_key="trace:abc",
        records=[LogRecord(message="x")],
    )
    item = append_log_query_evidence(pack, tool_name="log.query_by_trace_id", result=res)
    assert item.type.value == "log"
    assert len(pack.items) == 1


def test_append_tool_json_evidence() -> None:
    pack = EvidencePack(case_id="c1")
    append_tool_json_evidence(
        pack,
        tool_name="trace.get_chain",
        evidence_type=EvidenceType.TRACE,
        content={"trace_id": "t1"},
    )
    assert pack.items[0].type == EvidenceType.TRACE
