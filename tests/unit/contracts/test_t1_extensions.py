from rootseeker.contracts.common import Page, PagedResult
from rootseeker.contracts.errors import ErrorShape, FailureEnvelope, StandardErrorCode
from rootseeker.contracts.evidence import CodeEvidence, CodeHit, TraceChainEvidence, TraceSpanRef
from rootseeker.contracts.log_query import LogQueryTemplate
from rootseeker.contracts.log_source import LogSource


def test_paged_result() -> None:
    page = Page(offset=0, limit=10)
    pr = PagedResult(items=[{"id": 1}], total=100, page=page)
    assert pr.total == 100
    assert len(pr.items) == 1


def test_log_source_and_template() -> None:
    src = LogSource(
        type="sls",
        source_id="src-1",
        project="p",
        store="s",
        secret_ref="env:SLS_KEY",
    )
    tpl = LogQueryTemplate(
        template_id="errors.by_service",
        render_kind="sls_sql",
        template_body="* | select ...",
        parameter_schema={"type": "object"},
    )
    assert src.model_dump(mode="json")["type"] == "sls"
    assert tpl.template_id == "errors.by_service"


def test_trace_and_code_evidence() -> None:
    chain = TraceChainEvidence(
        trace_id="t1",
        spans=[
            TraceSpanRef(span_id="a", operation_name="GET /api"),
            TraceSpanRef(span_id="b", parent_span_id="a", operation_name="query_db"),
        ],
    )
    code = CodeEvidence(
        query="timeout",
        hits=[CodeHit(path="svc/main.go", line_start=42, snippet="ctx.Done()")],
    )
    assert len(chain.spans) == 2
    assert code.hits[0].line_start == 42


def test_failure_envelope() -> None:
    env = FailureEnvelope(
        error=ErrorShape(code=StandardErrorCode.NOT_FOUND, message="nope"),
    )
    assert env.ok is False
    assert env.error.code == "not_found"
