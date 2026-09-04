from pathlib import Path

from rootseeker.agent_runtime import (
    AgentRunLoop,
    AgentRuntime,
    ContextCompactor,
    ModelRoute,
    ToolExecutionTrace,
    ToolPlan,
    ToolPlanCall,
    ToolPlanResult,
)
from rootseeker.agent_runtime.attempt_runner import AttemptRunner
from rootseeker.agent_runtime.model_router import ModelRouter
from rootseeker.agent_runtime.tool_call_loop import ToolCallExecution
from rootseeker.agent_runtime.tool_plan import (
    enrich_tool_arguments_with_step_outputs,
    parse_tool_plan_content,
)
from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest, CaseStatus, StepStatus
from rootseeker.contracts.tool import ToolCallResult
from rootseeker.flow_runtime import FlowRuntime


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime(monkeypatch):
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    return create_dev_runtime(_repo_root())


def _agent_with_stub_planner(runtime):
    flow_runtime = FlowRuntime(runtime)
    attempt_runner = AttemptRunner(
        flow_runtime,
        model_router=_StaticRouter(),
        tool_planner=_StaticPlanner(),
    )
    return AgentRuntime(
        runtime,
        flow_runtime=flow_runtime,
        run_loop=AgentRunLoop(
            runtime,
            flow_runtime=flow_runtime,
            attempt_runner=attempt_runner,
        ),
    )


def test_agent_runtime_can_run_payload(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    agent = _agent_with_stub_planner(runtime)
    case_id = agent.run_payload(
        {
            "title": "agent runtime case",
            "service_name": "order-service",
            "message": "error ratio high in prod",
            "source": "unit-agent",
            "trace_id": "trace-agent-001",
        }
    )
    assert case_id.startswith("case-")


def test_agent_runtime_returns_detailed_run_result(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    agent = _agent_with_stub_planner(runtime)
    result = agent.run_payload_detailed(
        {
            "title": "agent runtime detailed case",
            "service_name": "order-service",
            "message": "error ratio high in prod",
            "source": "unit-agent",
            "trace_id": "trace-agent-002",
        }
    )
    assert result.case_id.startswith("case-")
    assert result.status == "completed"
    assert result.compacted_context is not None

    attempt = result.attempts[0]
    assert attempt.case_id == result.case_id
    assert attempt.route.mode == "llm_tool_plan"
    assert attempt.prompt_messages[0]["role"] == "system"
    assert any(trace.tool_name == "log.query_by_trace_id" for trace in attempt.tool_traces)

    actions = [event.action for event in runtime.audit_log.list_events(case_id=result.case_id, limit=-1)]
    assert "agent.attempt.completed" in actions
    assert "agent.tool.trace" in actions
    assert "agent.run.completed" in actions


def test_agent_runtime_streams_run_events(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    agent = _agent_with_stub_planner(runtime)

    events = list(
        agent.run_payload_stream(
            {
                "title": "agent runtime streamed case",
                "service_name": "order-service",
                "message": "error ratio high in prod",
                "source": "unit-agent",
                "trace_id": "trace-agent-stream-001",
            }
        )
    )

    event_types = [event.event_type for event in events]
    assert event_types[0] == "agent.run.started"
    assert "agent.attempt.completed" in event_types
    assert "agent.tool.trace" in event_types
    assert event_types[-1] == "agent.run.completed"
    assert events[-1].result is not None
    assert events[-1].result.status == "completed"
    assert events[-1].payload["attempt_count"] == 1

    actions = [event.action for event in runtime.audit_log.list_events(case_id=events[-1].result.case_id, limit=-1)]
    assert "agent.run.completed" in actions


def test_context_compactor_keeps_failed_and_recent_steps() -> None:
    traces = [
        ToolExecutionTrace(step_id=f"step-{idx}", tool_name=f"tool.{idx}", ok=(idx != 2))
        for idx in range(8)
    ]
    compacted = ContextCompactor(max_tool_traces=3).compact(
        prompt_messages=[{"role": "user", "content": "large history"}],
        tool_traces=traces,
    )
    assert compacted.compacted is True
    assert "step-2" in compacted.retained_step_ids
    assert compacted.retained_step_ids[-3:] == ["step-5", "step-6", "step-7"]
    assert "step-0" in compacted.omitted_step_ids


def test_parse_tool_plan_filters_unknown_tools_and_fills_defaults() -> None:
    case_request = CaseCreateRequest(
        title="planner",
        symptom="db timeout",
        service_name="order-service",
        source="unit-agent",
        metadata={"trace_id": "trace-plan-001"},
    )
    plan = parse_tool_plan_content(
        """
        ```json
        {
          "rationale": "Need logs first",
          "tool_calls": [
            {"step_id": "resolve-service", "tool_name": "catalog.resolve_service", "arguments": {}},
            {
              "step_id": "query-logs",
              "tool_name": "log.query_by_trace_id",
              "arguments": {},
              "depends_on": ["resolve-service", "missing-step", "query-logs"],
              "timeout_seconds": "12.5",
              "required": false
            },
            {"tool_name": "unknown.tool", "arguments": {}}
          ]
        }
        ```
        """,
        allowed_tools={"catalog.resolve_service", "log.query_by_trace_id"},
        max_tool_calls=4,
        case_request=case_request,
    )
    assert plan is not None
    assert len(plan.tool_calls) == 2
    assert plan.tool_calls[1].arguments["trace_id"] == "trace-plan-001"
    assert plan.tool_calls[1].arguments["service_name"] == "order-service"
    assert plan.tool_calls[1].depends_on == ["resolve-service"]
    assert plan.tool_calls[1].timeout_seconds == 12.5
    assert plan.tool_calls[1].required is False


def test_parse_tool_plan_prefers_llm_file_path_over_framework_default() -> None:
    stack = """
org.springframework.jdbc.UncategorizedSQLException: AES解密失败
	at org.springframework.jdbc.support.AbstractFallbackSQLExceptionTranslator.translate(AbstractFallbackSQLExceptionTranslator.java:89)
Caused by: java.lang.IllegalArgumentException: Input byte array has wrong 4-byte ending unit
	at java.util.Base64$Decoder.decode0(Base64.java:704)
	at net.coolcollege.usercenter.facade.utils.AesEncryptUtil.decrypt(AesEncryptUtil.java:61)
"""
    case_request = CaseCreateRequest(
        title="planner",
        symptom=stack,
        service_name="training-manage-api",
        source="unit-agent",
    )
    plan = parse_tool_plan_content(
        """
        {
          "rationale": "read decrypt util",
          "tool_calls": [
            {
              "step_id": "read-aes",
              "tool_name": "code.read",
              "arguments": {
                "file_path": "net/coolcollege/usercenter/facade/utils/AesEncryptUtil.java",
                "repo": "user-center-api"
              }
            }
          ]
        }
        """,
        allowed_tools={"code.read"},
        max_tool_calls=4,
        case_request=case_request,
    )
    assert plan is not None
    args = plan.tool_calls[0].arguments
    assert args["path"] == "net/coolcollege/usercenter/facade/utils/AesEncryptUtil.java"
    assert "AbstractFallbackSQLExceptionTranslator.java" not in str(args.get("path"))
    assert args["repo"] == "user-center-api"


def test_enrich_find_callers_injects_normalize_call_chain() -> None:
    args = enrich_tool_arguments_with_step_outputs(
        "code.find_callers",
        {
            "symbol": "BizPracticeService.queryBizPracticeListByUserDepaGroupPost",
            "_skip_reason": "No call_chain from normalize-incident.",
        },
        case_request=CaseCreateRequest(
            title="t",
            symptom="AES decrypt failed",
            service_name="training-manage-api",
            source="unit-agent",
        ),
        step_outputs={
            "llm-1-incident-normalize": {
                "extracted": {
                    "call_chain": [
                        "AesTypeHandler.decryptField (AesTypeHandler.java:53)",
                    ]
                }
            }
        },
    )
    assert args["call_chain"][0].startswith("AesTypeHandler.decryptField")
    assert "_skip_reason" not in args


def test_enrich_code_read_injects_focus_line_from_call_chain() -> None:
    args = enrich_tool_arguments_with_step_outputs(
        "code.read",
        {
            "path": (
                "user-center-service/src/main/java/net/coolcollege/usercenter/"
                "service/business/impl/SysUserGroupService.java"
            ),
            "repo": "user-center-api",
        },
        case_request=CaseCreateRequest(
            title="t",
            symptom="无法识别文件",
            service_name="user-center-api",
            source="unit-agent",
        ),
        step_outputs={
            "normalize": {
                "extracted": {
                    "call_chain": [
                        "SysUserGroupService.parseFile (SysUserGroupService.java:1333)",
                        "SysUserGroupControllerV2.parse (SysUserGroupControllerV2.java:172)",
                    ]
                }
            }
        },
    )
    assert args["line"] == 1333
    assert args["methods"] == ["parseFile"]
    assert args["path"].endswith("SysUserGroupService.java")


def test_parse_tool_plan_forces_code_read_to_depend_on_normalize() -> None:
    plan = parse_tool_plan_content(
        """
        {
          "rationale": "read business file",
          "tool_calls": [
            {"step_id": "1", "tool_name": "incident.normalize", "arguments": {}},
            {
              "step_id": "5",
              "tool_name": "code.read",
              "arguments": {"path": "AesTypeHandler.java", "repo": "user-center-api"},
              "depends_on": []
            }
          ]
        }
        """,
        allowed_tools={"incident.normalize", "code.read"},
        max_tool_calls=6,
        case_request=CaseCreateRequest(
            title="t",
            symptom="AES",
            service_name="training-manage-api",
            source="unit-agent",
        ),
    )
    assert plan is not None
    read = next(call for call in plan.tool_calls if call.tool_name == "code.read")
    assert "1" in read.depends_on


def test_enrich_code_read_maps_focus_method_alias() -> None:
    args = enrich_tool_arguments_with_step_outputs(
        "code.read",
        {
            "path": "SysUserGroupService.java",
            "repo": "user-center-api",
            "focus_method": "parseFile",
        },
        case_request=CaseCreateRequest(
            title="t",
            symptom="无法识别文件",
            service_name="user-center-api",
            source="unit-agent",
        ),
        step_outputs={},
    )
    assert args["methods"] == ["parseFile"]


def test_enrich_code_read_uses_symptom_stack_when_normalize_missing() -> None:
    stack = """
Caused by: java.sql.SQLException: AES解密失败
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField(AesTypeHandler.java:53)
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.getNullableResult(AesTypeHandler.java:28)
Caused by: java.lang.IllegalArgumentException: Input byte array has wrong 4-byte ending unit
	at net.coolcollege.usercenter.facade.utils.AesEncryptUtil.decrypt(AesEncryptUtil.java:61)
	at net.coolcollege.usercenter.facade.handler.AesTypeHandler.decryptField(AesTypeHandler.java:51)
"""
    args = enrich_tool_arguments_with_step_outputs(
        "code.read",
        {"path": "AesTypeHandler.java", "repo": "user-center-api"},
        case_request=CaseCreateRequest(
            title="t",
            symptom=stack,
            service_name="training-manage-api",
            source="unit-agent",
        ),
        step_outputs={},
    )
    assert args["methods"] == ["decryptField", "getNullableResult"]
    assert args["line"] in {51, 53, 28}


def test_agent_attempt_injects_call_chain_before_find_callers(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    tool_loop = _CaptureFindCallersLoop()
    attempt_runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_FindCallersPlanner(),
        tool_call_loop=tool_loop,
    )
    result = attempt_runner.run_once(
        CaseCreateRequest(
            title="find callers enrichment",
            symptom="AES decrypt failed",
            service_name="training-manage-api",
            source="unit-agent",
        )
    )
    assert result.status == "completed"
    assert tool_loop.find_callers_args is not None
    assert tool_loop.find_callers_args["call_chain"][0].startswith("AesTypeHandler.decryptField")


def test_agent_attempt_can_execute_llm_tool_plan(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    attempt_runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_StaticPlanner(),
    )
    result = attempt_runner.run_once(
        CaseCreateRequest(
            title="llm planned case",
            symptom="5xx from order service",
            service_name="order-service",
            source="unit-agent",
            metadata={"trace_id": "trace-agent-plan-001"},
        )
    )
    assert result.status == "completed"
    assert result.route.mode == "llm_tool_plan"
    assert [trace.tool_name for trace in result.tool_traces if trace.tool_name != "notify.send"] == [
        "catalog.resolve_service",
        "log.query_by_trace_id",
    ]
    assert result.tool_traces[-1].tool_name == "notify.send"
    assert result.tool_traces[1].plan_metadata["depends_on"] == ["resolve-service"]
    assert result.tool_traces[1].plan_metadata["timeout_seconds"] == 30.0
    assert result.tool_traces[1].plan_metadata["required"] is True
    assert runtime.case_store.get(result.case_id) is not None
    case = runtime.case_store.get(result.case_id)
    assert case is not None
    assert case.status == CaseStatus.COMPLETED
    assert all(step.status == StepStatus.COMPLETED for step in case.steps)
    pack = runtime.evidence_store.get_pack(result.case_id)
    assert pack is not None
    sources = [item.source for item in pack.items]
    assert "catalog.resolve_service" in sources
    assert "log.query_by_trace_id" not in sources
    assert "日志后端未配置" in pack.summary
    report = runtime.report_store.get(result.case_id)
    assert report is not None
    assert report.metadata["agent"]["route_mode"] == "llm_tool_plan"


def test_agent_run_loop_retries_llm_plan_with_history(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    flow_runtime = FlowRuntime(runtime)
    planner = _SequencePlanner()
    attempt_runner = AttemptRunner(
        flow_runtime,
        model_router=_StaticRouter(),
        tool_planner=planner,
    )
    run_loop = AgentRunLoop(
        runtime,
        flow_runtime=flow_runtime,
        attempt_runner=attempt_runner,
        max_attempts=2,
    )
    result = run_loop.run(
        CaseCreateRequest(
            title="self repair case",
            symptom="5xx from order service",
            service_name="order-service",
            source="unit-agent",
            metadata={"trace_id": "trace-agent-repair-001"},
        )
    )
    assert result.status == "completed"
    assert len(result.attempts) == 2
    assert result.attempts[0].status == "failed"
    assert result.attempts[1].status == "completed"
    assert planner.history_summaries[0] is None
    assert planner.history_summaries[1] is not None
    assert "planner_error=temporary planner failure" in planner.history_summaries[1]

    actions = [event.action for event in runtime.audit_log.list_events(limit=-1)]
    assert "agent.attempt.retrying" in actions


def test_agent_attempt_skips_steps_with_failed_dependencies(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    attempt_runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_DependentPlanner(),
        tool_call_loop=_FailFirstToolLoop(),
    )
    result = attempt_runner.run_once(
        CaseCreateRequest(
            title="dependent plan case",
            symptom="5xx from order service",
            service_name="order-service",
            source="unit-agent",
            metadata={"trace_id": "trace-agent-dep-001"},
        )
    )

    assert result.status == "failed"
    assert [trace.step_id for trace in result.tool_traces if trace.tool_name != "notify.send"] == [
        "resolve-service",
        "query-logs",
    ]
    assert result.tool_traces[0].error_code == "UNIT_FAILURE"
    assert result.tool_traces[1].error_code == "DEPENDENCY_FAILED"
    assert result.tool_traces[1].plan_metadata["depends_on"] == ["resolve-service"]


def test_agent_attempt_continues_after_optional_dependency_failure(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    attempt_runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_OptionalDependencyPlanner(),
        tool_call_loop=_FailOptionalToolLoop(),
    )
    result = attempt_runner.run_once(
        CaseCreateRequest(
            title="optional dependency plan case",
            symptom="5xx from order service",
            service_name="order-service",
            source="unit-agent",
            metadata={"trace_id": "trace-agent-optional-001"},
        )
    )

    assert result.status == "completed"
    assert [trace.step_id for trace in result.tool_traces if trace.tool_name != "notify.send"] == [
        "optional-code-search",
        "query-logs",
    ]
    assert result.tool_traces[0].error_code == "OPTIONAL_FAILURE"
    assert result.tool_traces[0].plan_metadata["required"] is False
    assert result.tool_traces[1].ok is True


def test_agent_attempt_batches_independent_ready_steps(monkeypatch) -> None:
    runtime = _runtime(monkeypatch)
    tool_loop = _RecordingToolLoop()
    attempt_runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_ParallelPlanner(),
        tool_call_loop=tool_loop,
    )
    result = attempt_runner.run_once(
        CaseCreateRequest(
            title="parallel plan case",
            symptom="5xx from order service",
            service_name="order-service",
            source="unit-agent",
            metadata={"trace_id": "trace-agent-parallel-001"},
        )
    )

    assert result.status == "completed"
    assert tool_loop.batches[:2] == [
        ["resolve-service", "query-logs"],
        ["search-code"],
    ]
    assert tool_loop.batches[-1] == ["notify"]
    assert [trace.step_id for trace in result.tool_traces if trace.tool_name != "notify.send"] == [
        "resolve-service",
        "query-logs",
        "search-code",
    ]


class _StaticRouter(ModelRouter):
    def select_route(self, case_request: CaseCreateRequest) -> ModelRoute:
        return ModelRoute(
            mode="llm_tool_plan",
            provider_name="unit",
            model="planner",
            reason="unit test",
            metadata={"service_name": case_request.service_name},
        )


class _StaticPlanner:
    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None) -> ToolPlanResult:
        return ToolPlanResult(
            ok=True,
            provider="unit",
            model="planner",
            plan=ToolPlan(
                rationale="unit planned",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="catalog.resolve_service",
                        step_id="resolve-service",
                        arguments={
                            "tenant": "demo",
                            "environment": "prod",
                            "service_name": case_request.service_name,
                        },
                    ),
                    ToolPlanCall(
                        tool_name="log.query_by_trace_id",
                        step_id="query-logs",
                        arguments={
                            "trace_id": case_request.metadata["trace_id"],
                            "service_name": case_request.service_name,
                        },
                        depends_on=["resolve-service"],
                        timeout_seconds=30.0,
                    ),
                ],
            ),
        )


class _SequencePlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.history_summaries: list[str | None] = []

    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None) -> ToolPlanResult:
        self.calls += 1
        self.history_summaries.append(history_summary)
        if self.calls == 1:
            return ToolPlanResult(
                ok=False,
                provider="unit",
                model="planner",
                error="temporary planner failure",
            )
        return _StaticPlanner().plan(
            case_request=case_request,
            tools=tools,
            history_summary=history_summary,
        )


class _DependentPlanner:
    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None) -> ToolPlanResult:
        return ToolPlanResult(
            ok=True,
            provider="unit",
            model="planner",
            plan=ToolPlan(
                rationale="unit planned dependencies",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="catalog.resolve_service",
                        step_id="resolve-service",
                        arguments={
                            "tenant": "demo",
                            "environment": "prod",
                            "service_name": case_request.service_name,
                        },
                    ),
                    ToolPlanCall(
                        tool_name="log.query_by_trace_id",
                        step_id="query-logs",
                        arguments={
                            "trace_id": case_request.metadata["trace_id"],
                            "service_name": case_request.service_name,
                        },
                        depends_on=["resolve-service"],
                    ),
                ],
            ),
        )


class _FailFirstToolLoop:
    def execute_records(self, requests, *, plugin_id=None, actor="agent-runtime", plan_metadata_by_step_id=None):
        request = requests[0]
        if request.tool_name == "notify.send":
            result = ToolCallResult(ok=True, tool_name=request.tool_name, content={"ok": True})
            trace = ToolExecutionTrace(
                step_id=request.step_id,
                tool_name=request.tool_name,
                ok=True,
                content_preview=result.content,
                plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id, {}),
            )
            return [ToolCallExecution(request=request, result=result, trace=trace)]
        result = ToolCallResult(
            ok=False,
            tool_name=request.tool_name,
            error={"code": "UNIT_FAILURE", "message": "forced failure", "retryable": False},
        )
        trace = ToolExecutionTrace(
            step_id=request.step_id,
            tool_name=request.tool_name,
            ok=False,
            error_code="UNIT_FAILURE",
            error_message="forced failure",
            plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id, {}),
        )
        return [ToolCallExecution(request=request, result=result, trace=trace)]


class _OptionalDependencyPlanner:
    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None) -> ToolPlanResult:
        return ToolPlanResult(
            ok=True,
            provider="unit",
            model="planner",
            plan=ToolPlan(
                rationale="unit planned optional dependency",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="code.search",
                        step_id="optional-code-search",
                        arguments={"query": case_request.symptom},
                        required=False,
                    ),
                    ToolPlanCall(
                        tool_name="log.query_by_trace_id",
                        step_id="query-logs",
                        arguments={
                            "trace_id": case_request.metadata["trace_id"],
                            "service_name": case_request.service_name,
                        },
                        depends_on=["optional-code-search"],
                    ),
                ],
            ),
        )


class _FailOptionalToolLoop:
    def execute_records(self, requests, *, plugin_id=None, actor="agent-runtime", plan_metadata_by_step_id=None):
        request = requests[0]
        plan_metadata = (plan_metadata_by_step_id or {}).get(request.step_id, {})
        if request.tool_name == "notify.send":
            result = ToolCallResult(ok=True, tool_name=request.tool_name, content={"ok": True})
            trace = ToolExecutionTrace(
                step_id=request.step_id,
                tool_name=request.tool_name,
                ok=True,
                content_preview=result.content,
                plan_metadata=plan_metadata,
            )
            return [ToolCallExecution(request=request, result=result, trace=trace)]
        if request.step_id == "optional-code-search":
            result = ToolCallResult(
                ok=False,
                tool_name=request.tool_name,
                error={"code": "OPTIONAL_FAILURE", "message": "optional failed", "retryable": False},
            )
            trace = ToolExecutionTrace(
                step_id=request.step_id,
                tool_name=request.tool_name,
                ok=False,
                error_code="OPTIONAL_FAILURE",
                error_message="optional failed",
                plan_metadata=plan_metadata,
            )
            return [ToolCallExecution(request=request, result=result, trace=trace)]

        result = ToolCallResult(
            ok=True,
            tool_name=request.tool_name,
            content={"rows": [{"trace_id": request.arguments["trace_id"]}]},
        )
        trace = ToolExecutionTrace(
            step_id=request.step_id,
            tool_name=request.tool_name,
            ok=True,
            content_preview=result.content,
            plan_metadata=plan_metadata,
        )
        return [ToolCallExecution(request=request, result=result, trace=trace)]


class _ParallelPlanner:
    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None) -> ToolPlanResult:
        return ToolPlanResult(
            ok=True,
            provider="unit",
            model="planner",
            plan=ToolPlan(
                rationale="unit planned parallel waves",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="catalog.resolve_service",
                        step_id="resolve-service",
                        arguments={
                            "tenant": "demo",
                            "environment": "prod",
                            "service_name": case_request.service_name,
                        },
                    ),
                    ToolPlanCall(
                        tool_name="log.query_by_trace_id",
                        step_id="query-logs",
                        arguments={
                            "trace_id": case_request.metadata["trace_id"],
                            "service_name": case_request.service_name,
                        },
                    ),
                    ToolPlanCall(
                        tool_name="code.search",
                        step_id="search-code",
                        arguments={"query": case_request.symptom},
                        depends_on=["resolve-service", "query-logs"],
                    ),
                ],
            ),
        )


class _RecordingToolLoop:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def execute_records(self, requests, *, plugin_id=None, actor="agent-runtime", plan_metadata_by_step_id=None):
        self.batches.append([request.step_id for request in requests])
        records = []
        for request in requests:
            content = {"ok": True, "step_id": request.step_id}
            result = ToolCallResult(ok=True, tool_name=request.tool_name, content=content)
            trace = ToolExecutionTrace(
                step_id=request.step_id,
                tool_name=request.tool_name,
                ok=True,
                content_preview=content,
                plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id, {}),
            )
            records.append(ToolCallExecution(request=request, result=result, trace=trace))
        return records


class _FindCallersPlanner:
    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None) -> ToolPlanResult:
        return ToolPlanResult(
            ok=True,
            provider="unit",
            model="planner",
            plan=ToolPlan(
                rationale="normalize then find callers",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="incident.normalize",
                        step_id="llm-1-incident-normalize",
                        arguments={"payload": {"message": case_request.symptom}},
                    ),
                    ToolPlanCall(
                        tool_name="code.find_callers",
                        step_id="llm-2-code-find-callers",
                        arguments={
                            "symbol": "BizPracticeService.queryBizPracticeListByUserDepaGroupPost",
                            "_skip_reason": "No call_chain from normalize-incident.",
                        },
                        depends_on=["llm-1-incident-normalize"],
                    ),
                ],
            ),
        )


class _CaptureFindCallersLoop:
    def __init__(self) -> None:
        self.find_callers_args: dict | None = None

    def execute_records(self, requests, *, plugin_id=None, actor="agent-runtime", plan_metadata_by_step_id=None):
        records = []
        for request in requests:
            if request.tool_name == "incident.normalize":
                content = {
                    "extracted": {
                        "call_chain": [
                            "AesTypeHandler.decryptField (AesTypeHandler.java:53)",
                        ]
                    }
                }
            elif request.tool_name == "notify.send":
                content = {"ok": True}
            else:
                self.find_callers_args = dict(request.arguments)
                content = {"ok": True, "static_callers": []}
            result = ToolCallResult(ok=True, tool_name=request.tool_name, content=content)
            trace = ToolExecutionTrace(
                step_id=request.step_id,
                tool_name=request.tool_name,
                ok=True,
                content_preview=content,
                plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id, {}),
            )
            records.append(ToolCallExecution(request=request, result=result, trace=trace))
        return records
