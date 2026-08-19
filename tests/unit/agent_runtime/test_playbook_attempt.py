from pathlib import Path

from rootseeker.agent_runtime.attempt_runner import AttemptRunner
from rootseeker.agent_runtime.llm_tool_planner import build_tool_planner_messages
from rootseeker.agent_runtime.model_router import ModelRouter
from rootseeker.agent_runtime.result import ModelRoute, ToolExecutionTrace
from rootseeker.agent_runtime.tool_call_loop import ToolCallExecution
from rootseeker.agent_runtime.tool_plan import ToolPlan, ToolPlanCall, ToolPlanResult
from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.skill import SkillKind, SkillSpec
from rootseeker.contracts.tool import ToolCallResult
from rootseeker.flow_runtime import FlowRuntime


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _case_request(**metadata: object) -> CaseCreateRequest:
    return CaseCreateRequest(
        title="t",
        symptom="boom",
        service_name="s",
        source="webhook",
        metadata=dict(metadata),
    )


class _StaticRouter(ModelRouter):
    def select_route(self, case_request: CaseCreateRequest) -> ModelRoute:
        return ModelRoute(
            mode="llm_tool_plan",
            provider_name="unit",
            model="planner",
            reason="unit test",
            metadata={"service_name": case_request.service_name},
        )


class _FailingPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None, **kwargs):
        self.calls += 1
        return ToolPlanResult(
            ok=False,
            provider="unit",
            model="planner",
            error="forced planner failure",
        )


class _DisallowedToolPlanner:
    def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None, **kwargs):
        return ToolPlanResult(
            ok=True,
            provider="unit",
            model="planner",
            plan=ToolPlan(
                rationale="call a tool outside the playbook allow-list",
                tool_calls=[
                    ToolPlanCall(
                        tool_name="shell.exec",
                        step_id="disallowed-shell",
                        arguments={"command": "id"},
                    )
                ],
            ),
        )


class _RecordingToolLoop:
    def __init__(self) -> None:
        self.executed_tools: list[str] = []

    def execute_records(self, requests, *, plugin_id=None, actor="agent-runtime", plan_metadata_by_step_id=None):
        records = []
        for request in requests:
            self.executed_tools.append(request.tool_name)
            result = ToolCallResult(ok=True, tool_name=request.tool_name, content={"ok": True})
            trace = ToolExecutionTrace(
                step_id=request.step_id,
                tool_name=request.tool_name,
                ok=True,
                content_preview=result.content,
                plan_metadata=(plan_metadata_by_step_id or {}).get(request.step_id, {}),
            )
            records.append(ToolCallExecution(request=request, result=result, trace=trace))
        return records


def test_planner_messages_include_playbook_not_unloaded_helper_body() -> None:
    messages = build_tool_planner_messages(
        case_request=CaseCreateRequest(title="t", symptom="boom", service_name="s", source="webhook"),
        tools=[],
        max_tool_calls=4,
        playbook_text="# default-log-triage\nCall incident.normalize first.",
        skill_catalog=[{"name": "code-lookup", "description": "Search code"}],
        allowed_tool_names={"incident.normalize"},
    )
    blob = messages[1]["content"]
    assert "Call incident.normalize first" in blob
    assert "code-lookup" in blob
    assert "Use file: query" not in blob  # helper 正文不得出现


def test_attempt_runner_does_not_call_execute_skill_flow(monkeypatch) -> None:
    import importlib

    skill_runtime = importlib.import_module("rootseeker.skill_runtime")
    assert not hasattr(skill_runtime, "execute_skill_flow")
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(_repo_root())
    planner = _FailingPlanner()
    runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=planner,
    )
    result = runner.run_once(_case_request(), allow_default_fallback=False)
    assert result.status == "failed"
    assert result.metadata.get("error_code") == "SKILL_PLANNER_FAILED"


def test_disallowed_tool_fails_without_executing(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(_repo_root())
    tool_loop = _RecordingToolLoop()
    runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_DisallowedToolPlanner(),
        tool_call_loop=tool_loop,
    )
    result = runner.run_once(_case_request(), allow_default_fallback=False)
    assert tool_loop.executed_tools == []
    assert result.status == "failed"
    assert result.metadata.get("error_code") == "SKILL_TOOL_NOT_ALLOWED"


def test_missing_playbook_env_fails_without_planning(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(_repo_root())
    runtime.skill_registry.upsert(
        SkillSpec(
            name="env-playbook",
            slug="env-playbook",
            description="requires a missing env key",
            skill_kind=SkillKind.FLOW,
            bound_tools=["incident.normalize"],
            metadata={
                "role": "playbook",
                "env": ["ROOTSEEKER_TEST_MISSING_SKILL_ENV_XYZ"],
            },
        )
    )
    planner = _FailingPlanner()
    runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=planner,
    )
    result = runner.run_once(
        _case_request(preferred_skill="env-playbook"),
        allow_default_fallback=False,
    )
    assert planner.calls == 0
    assert result.status == "failed"
    assert result.metadata.get("error_code") == "SKILL_ENV_MISSING"


def test_skill_env_overlay_survives_provider_refresh_during_plan(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    monkeypatch.setenv("SKILL_KEY", "secret")
    runtime = create_dev_runtime(_repo_root())
    runtime.mcp_server_manager.set_extra_env_provider(lambda: {"RUNTIME": "a"})

    runtime.skill_registry.upsert(
        SkillSpec(
            name="env-overlay-playbook",
            slug="env-overlay-playbook",
            description="injects skill env for this run",
            skill_kind=SkillKind.FLOW,
            bound_tools=["incident.normalize"],
            metadata={"role": "playbook", "env": ["SKILL_KEY"]},
        )
    )

    class _EnvSpyPlanner:
        def __init__(self) -> None:
            self.env_during_plan: dict[str, str] | None = None

        def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None, **kwargs):
            self.env_during_plan = dict(runtime.mcp_server_manager.extra_env)
            return ToolPlanResult(ok=False, provider="unit", model="planner", error="stop after spy")

    planner = _EnvSpyPlanner()
    runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=planner,
    )
    runner.run_once(_case_request(preferred_skill="env-overlay-playbook"), allow_default_fallback=False)
    assert planner.env_during_plan is not None
    assert planner.env_during_plan.get("RUNTIME") == "a"
    assert planner.env_during_plan.get("SKILL_KEY") == "secret"
    after = runtime.mcp_server_manager.extra_env
    assert "SKILL_KEY" not in after


def test_loaded_helper_bound_tools_are_unioned_into_allow_list(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(_repo_root())
    runtime.skill_registry.upsert(
        SkillSpec(
            name="narrow-playbook",
            slug="narrow-playbook",
            description="only incident.normalize",
            skill_kind=SkillKind.FLOW,
            bound_tools=["incident.normalize"],
            metadata={"role": "playbook"},
        )
    )
    helper = SkillSpec(
        name="graph-lookup",
        slug="graph-lookup",
        description="graph helper",
        skill_kind=SkillKind.TOOL,
        bound_tools=["graph.cypher"],
        metadata={"role": "helper"},
    )

    class _GraphCypherPlanner:
        def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None, **kwargs):
            return ToolPlanResult(
                ok=True,
                provider="unit",
                model="planner",
                plan=ToolPlan(
                    rationale="call helper-only tool",
                    tool_calls=[
                        ToolPlanCall(tool_name="graph.cypher", step_id="graph-1", arguments={"q": "MATCH (n) RETURN n"})
                    ],
                ),
            )

    tool_loop = _RecordingToolLoop()
    runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=_GraphCypherPlanner(),
        tool_call_loop=tool_loop,
    )
    blocked = runner.run_once(
        _case_request(preferred_skill="narrow-playbook"),
        allow_default_fallback=False,
    )
    assert tool_loop.executed_tools == []
    assert blocked.status == "failed"
    assert blocked.metadata.get("error_code") == "SKILL_TOOL_NOT_ALLOWED"

    runner.loaded_helpers = [helper]
    allowed = runner.run_once(
        _case_request(preferred_skill="narrow-playbook"),
        allow_default_fallback=False,
    )
    assert "graph.cypher" in tool_loop.executed_tools
    assert allowed.status == "completed"
    assert allowed.metadata.get("error_code") is None


def test_playbook_write_tools_reach_planner_and_omitted_notify_is_skipped(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    runtime = create_dev_runtime(_repo_root())
    runtime.skill_registry.upsert(
        SkillSpec(
            name="notify-playbook",
            slug="notify-playbook",
            description="lists notify.send",
            skill_kind=SkillKind.FLOW,
            bound_tools=["incident.normalize", "notify.send"],
            metadata={"role": "playbook"},
        )
    )

    class _CapturingPlanner:
        allow_write_tools = False

        def __init__(self) -> None:
            self.seen_tool_names: list[str] = []

        def plan(self, *, case_request: CaseCreateRequest, tools, history_summary=None, **kwargs):
            self.seen_tool_names = [getattr(tool, "name", str(tool)) for tool in tools]
            return ToolPlanResult(
                ok=True,
                provider="unit",
                model="planner",
                plan=ToolPlan(
                    rationale="omit notify",
                    tool_calls=[
                        ToolPlanCall(tool_name="incident.normalize", step_id="n1", arguments={})
                    ],
                ),
            )

    planner = _CapturingPlanner()
    tool_loop = _RecordingToolLoop()
    runner = AttemptRunner(
        FlowRuntime(runtime),
        model_router=_StaticRouter(),
        tool_planner=planner,
        tool_call_loop=tool_loop,
    )
    result = runner.run_once(
        _case_request(preferred_skill="notify-playbook"),
        allow_default_fallback=False,
    )
    assert "notify.send" in planner.seen_tool_names
    assert result.status == "completed"
    assert result.metadata.get("notify_skipped") is True
    report = runtime.report_store.get(result.case_id)
    assert report is not None
    assert report.metadata.get("notify_skipped") is True
