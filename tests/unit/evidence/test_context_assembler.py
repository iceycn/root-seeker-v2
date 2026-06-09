from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.evidence import append_tool_json_evidence, build_context_window


def test_context_window_from_evidence_pack() -> None:
    pack = EvidencePack(case_id="c1")
    append_tool_json_evidence(
        pack,
        tool_name="trace.get_chain",
        evidence_type=EvidenceType.TRACE,
        content={"trace_id": "t1"},
    )
    cw = build_context_window(pack, max_tokens=512)
    assert cw.case_id == "c1"
    assert cw.used_tokens <= cw.max_tokens
    assert cw.segments
