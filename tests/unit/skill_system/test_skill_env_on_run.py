from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from apps.admin.main import create_app
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.mcp_plane.process_env import merge_stdio_env
from rootseeker.mcp_plane.stdio_session import McpStdioSession
from tests.support.stub_planner import IncidentNormalizePlanner

ECHO_SERVER = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"


def test_skill_scope_env_reaches_mcp_echo_env_after_install_and_set_default(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    playbook_dir = tmp_path / "pkg" / "env-playbook"
    playbook_dir.mkdir(parents=True)
    (playbook_dir / "SKILL.md").write_text(
        "---\n"
        "name: env-playbook\n"
        "description: playbook that declares a skill-scoped env key\n"
        "metadata:\n"
        "  role: playbook\n"
        "  env: [SKILL_ONLY_TOKEN]\n"
        "allowed-tools: incident.normalize\n"
        "---\n"
        "# Env playbook\n",
        encoding="utf-8",
    )

    app = create_app(tmp_path)
    client = TestClient(app)
    skill_only = client.post(
        "/api/env-vars",
        json={"key": "SKILL_ONLY_TOKEN", "value": "skill-secret-from-admin", "scope": "skill"},
    )
    assert skill_only.status_code == 200
    extra_env = app.state.runtime.mcp_server_manager.extra_env
    assert "SKILL_ONLY_TOKEN" not in extra_env

    installed = client.post("/api/skills/install", json={"source": str(playbook_dir.parent)})
    assert installed.status_code == 200
    setd = client.post("/api/skills/env-playbook/default")
    assert setd.status_code == 200

    captured: dict[str, str] = {}

    class _EchoEnvPlanner(IncidentNormalizePlanner):
        def plan(self, *, case_request, tools, history_summary=None, **kwargs):
            env = dict(app.state.runtime.mcp_server_manager.extra_env)
            captured.update(env)
            session = McpStdioSession(
                sys.executable,
                [str(ECHO_SERVER)],
                env=merge_stdio_env(extra_env=env, server_env={}),
            )
            try:
                result = session.call_tool("echo_env", {"key": "SKILL_ONLY_TOKEN"})
            finally:
                session.close()
            captured["echo_env"] = str(result.get("text") or "")
            return super().plan(
                case_request=case_request,
                tools=tools,
                history_summary=history_summary,
                **kwargs,
            )

    app.state.runtime.tool_planner = _EchoEnvPlanner()
    app.state.runtime.run_agent_from_case_request(
        CaseCreateRequest(
            title="env-on-run",
            symptom="boom",
            service_name="svc",
            source="test",
        )
    )

    assert captured.get("SKILL_ONLY_TOKEN") == "skill-secret-from-admin"
    assert captured.get("echo_env") == "skill-secret-from-admin"
    assert "SKILL_ONLY_TOKEN" not in app.state.runtime.mcp_server_manager.extra_env
