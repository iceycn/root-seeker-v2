import pytest
from pydantic import ValidationError

from rootseeker.contracts.case import CaseCreateRequest, CaseStep, StepStatus
from rootseeker.contracts.common import Page, RootSeekerModel, new_id
from rootseeker.contracts.errors import ErrorShape, StandardErrorCode
from rootseeker.contracts.execution_trace import ExecutionTrace, StepExecutionRecord
from rootseeker.contracts.flow import FlowSpec, FlowStepSpec
from rootseeker.contracts.indexing import IndexKind, IndexStatus
from rootseeker.contracts.log_query import LogQueryByTraceIdRequest, LogQueryResult, LogRecord
from rootseeker.contracts.plugin import PluginKind, PluginManifest
from rootseeker.contracts.replay import ReplayCaseSpec
from rootseeker.contracts.repository import RepositoryRef
from rootseeker.contracts.service_catalog import ServiceCatalogEntry
from rootseeker.contracts.task import TaskKind, TaskRecord, TaskStatus


def test_common_helpers_and_base() -> None:
    assert new_id("pre-").startswith("pre-")
    page = Page(offset=0, limit=10)
    assert page.limit == 10


def test_error_shape_and_standard_codes() -> None:
    err = ErrorShape(
        code=StandardErrorCode.NOT_FOUND,
        message="missing",
        details={"id": "x"},
    )
    assert err.model_dump(mode="json")["code"] == "not_found"


def test_plugin_flow_task_roundtrip_json() -> None:
    manifest = PluginManifest(
        plugin_id="builtin.service-catalog",
        kind=PluginKind.CONNECTOR,
        capabilities=["catalog.resolve_service"],
        mcp_tools=["catalog.resolve_service"],
    )
    flow = FlowSpec(
        flow_id="builtin.default_log_triage_flow",
        plugin_id="builtin.default_log_triage_flow",
        skill_slug="base/default-log-triage",
        steps=[
            FlowStepSpec(
                step_id="s1",
                name="resolve",
                capability="catalog.resolve_service",
            )
        ],
    )
    task = TaskRecord(
        task_id="t1",
        kind=TaskKind.CASE_RUN,
        case_id="c1",
        flow_id=flow.flow_id,
        skill_slug=flow.skill_slug,
        status=TaskStatus.PENDING,
    )
    assert manifest.plugin_id
    assert task.model_dump(mode="json")["kind"] == "case_run"


def test_service_catalog_log_query_repository_indexing() -> None:
    entry = ServiceCatalogEntry(
        tenant="t1",
        environment="prod",
        service_name="api",
        display_name="API",
        log_sources=[{"type": "sls", "project": "p"}],
    )
    q = LogQueryByTraceIdRequest(trace_id="tr-1")
    res = LogQueryResult(query_key="trace:tr-1", records=[LogRecord(message="hello")])
    repo = RepositoryRef(name="api", url="https://example/git", default_branch="main")
    idx = IndexStatus(index_name="zoekt-main", kind=IndexKind.ZOEKT, ready=True)
    payload = {
        "entry": entry.model_dump(mode="json"),
        "query": q.model_dump(mode="json"),
        "result": res.model_dump(mode="json"),
        "repo": repo.model_dump(mode="json"),
        "idx": idx.model_dump(mode="json"),
    }
    assert payload["entry"]["service_name"] == "api"
    assert len(payload["result"]["records"]) == 1


def test_replay_and_execution_trace() -> None:
    req = CaseCreateRequest(
        title="x",
        symptom="y",
        service_name="api",
        source="replay",
    )
    replay = ReplayCaseSpec(
        replay_id="rp-1",
        name="baseline",
        case_request=req,
        expected_report_bullets=["service=api"],
    )
    step = CaseStep(
        step_id="st-1",
        name="n",
        skill_name="base/default-log-triage",
        action="catalog.resolve_service",
        status=StepStatus.COMPLETED,
    )
    ex = ExecutionTrace(
        execution_id="ex-1",
        case_id="c-9",
        skill_slug="base/default-log-triage",
        steps=[
            StepExecutionRecord(
                step_id=step.step_id,
                name=step.name,
                status=StepStatus.COMPLETED,
                tool_name="catalog.resolve_service",
            )
        ],
    )
    assert replay.replay_id == "rp-1"
    assert ex.steps[0].tool_name == "catalog.resolve_service"


def test_root_seeker_model_rejects_unknown_field() -> None:
    class Sample(RootSeekerModel):
        a: int = 1

    s = Sample(a=2)
    assert s.a == 2
    with pytest.raises(ValidationError):
        Sample(a=1, bad=2)  # type: ignore[call-arg]
