from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.log_query import LogQueryResult, LogQueryTemplate
from rootseeker.log_data import (
    extract_trace_id,
    log_result_to_evidence,
    redact_log_result,
    render_query_template,
    resolve_time_window,
)


def test_log_template_render_and_time_window() -> None:
    tpl = LogQueryTemplate(template_id="t1", render_kind="sql", template_body="trace={{trace_id}}")
    q = render_query_template(tpl, {"trace_id": "abc"})
    assert q == "trace=abc"
    start, end = resolve_time_window(lookback_minutes=10)
    assert start and end


def test_trace_extract_redact_and_evidence_map() -> None:
    assert extract_trace_id({"trace_id": "x"}) == "x"
    result = LogQueryResult(query_key="k1", records=[])
    red = redact_log_result(result)
    assert red.metadata["redacted"] is True
    pack = EvidencePack(case_id="c1")
    log_result_to_evidence(pack=pack, tool_name="log.query_by_trace_id", result=result)
    assert len(pack.items) == 1
