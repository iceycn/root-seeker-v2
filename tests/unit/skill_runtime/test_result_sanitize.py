from __future__ import annotations

from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.skill_runtime.evidence_mapper import map_tool_result_to_evidence
from rootseeker.skill_runtime.result_sanitize import (
    EVIDENCE_MAX_CODE_HITS,
    sanitize_tool_result_for_evidence,
    sanitize_tool_result_for_persistence,
)


def test_sanitize_tool_result_truncates_code_hits() -> None:
    hits = [{"path": f"a{i}.py", "snippet": "x"} for i in range(500)]
    sanitized = sanitize_tool_result_for_persistence(
        {"query": "error", "hits": hits, "total": 500}
    )
    assert len(sanitized["hits"]) == 50
    assert sanitized["truncated"] is True
    assert sanitized["truncated_from"] == 500
    assert sanitized["total"] == 500


def test_sanitize_evidence_keeps_smaller_preview() -> None:
    hits = [{"path": f"a{i}.py"} for i in range(200)]
    evidence = sanitize_tool_result_for_evidence(
        "code.search",
        {"query": "error", "hits": hits, "total": 200},
    )
    assert len(evidence["hits"]) == EVIDENCE_MAX_CODE_HITS
    assert evidence["truncated"] is True


def test_map_tool_result_to_evidence_truncates_code_search() -> None:
    pack = EvidencePack(case_id="c1")
    hits = [{"path": f"f{i}.java", "snippet": "line"} for i in range(1000)]
    map_tool_result_to_evidence(
        pack=pack,
        action="code.search",
        content={"query": "error ratio", "hits": hits, "total": 1000},
    )
    assert len(pack.items) == 1
    assert pack.items[0].type == EvidenceType.CODE
    content = pack.items[0].content
    assert len(content["hits"]) == EVIDENCE_MAX_CODE_HITS
    assert content["truncated"] is True
    assert content["total"] == 1000
