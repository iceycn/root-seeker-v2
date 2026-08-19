# Task 11 Report: 全量回归与文档

**Branch:** `feat/standard-skills-replace-flow`  
**HEAD before start:** `f7847a45c846dc638771b18fbf1459ada03bb616`  
**Date:** 2026-08-19  
**Status:** DONE_WITH_CONCERNS

## Summary

Full unit + integration suite is green under Agent playbook semantics. Three failures were leftover YAML-Flow assumptions (CLI demo / Prometheus expected a completed run without an LLM planner). Tests now inject a stub planner; `execute_skill_flow` was not restored.

Grep guards pass on the repo tree (excluding gitignored `repos/` and `.venv`). Business-logic docs that still claimed the 14-step YAML stepper / sidecar as the default path were corrected. Spec status is 已实现.

## Commits

1. `4989e7f` — `fix(tests): stub planner so CLI demo and metrics run without YAML Flow`
2. `9bd8c3e` — `docs(skill): record Agent playbook as default path`

Did not push. Did not amend.

## Step 1 — pytest

Command:

```
uv run python -m pytest tests/unit tests/integration -q --tb=short
```

### First run (before test fixes)

Exit code 1. Three failures:

| Test | Observed | Root cause |
| --- | --- | --- |
| `tests/unit/apps/test_cli_entrypoints.py::test_cli_demo_command` | `status=failed`, `runner=default_flow` | `run_default_flow_from_case_request` now goes through Agent; no LLM planner → `SKILL_PLANNER_FAILED`. Previously YAML stepper completed offline. |
| `tests/unit/apps/test_cli_entrypoints.py::test_cli_demo_command_with_use_agent` | `status=failed`, `runner=agent`, `attempt_count=2` | `ROOTSEEKER_LLM_ENABLED=false` → planner missing; no Flow fallback. |
| `tests/unit/observability/test_observability_components.py::test_prometheus_metrics_include_agent_tool_and_approval_activity` | missing `agent.run.completed` | Same: planner fails → `agent.run.failed`; no tool events. |

Did **not** restore `execute_skill_flow`.

### Fix (new semantics)

- CLI tests monkeypatch `apps.cli.main.create_dev_runtime` to inject `IncidentNormalizePlanner` (same stub as integration / Task 8–10).
- Observability test injects a planner that calls `log.query_by_trace_id` (still in playbook `allowed-tools`) so Prometheus still records `agent.run.completed` and that tool metric.

Re-run of the three tests: pass.

### Second full run (after test fixes)

```
uv run python -m pytest tests/unit tests/integration -q --tb=short
```

Exit code **0**. Collected **592** tests (`--collect-only`). One Starlette/`httpx` deprecation warning from FastAPI TestClient (pre-existing). No failures.

## Step 2 — Grep 守卫

`rg` was not used. Windows equivalent (Python), recorded:

```
python -c "
from pathlib import Path
root = Path(r'e:/CodeProjects/root-seeker-v2')
skip = {'.venv','__pycache__','.git','repos','node_modules'}
# execute_skill_flow in *.py
# rootseeker-skill.yaml in *.yaml/*.yml
"
```

`repos/` is gitignored (nested clone of old tree) and was excluded so leftover sidecar copies there do not count as this repo's builtin.

### `execute_skill_flow` in `*.py`

**Production hits:** none (`rootseeker/`, `apps/`, `plugins/` clean).

**Test hits (negative assertions only):**

| File | Lines |
| --- | --- |
| `tests/unit/skill_runtime/test_execute_skill_flow_removed.py` | `hasattr` |
| `tests/unit/agent_runtime/test_playbook_attempt.py` | `test_attempt_runner_does_not_call_execute_skill_flow` + `hasattr` |
| `tests/integration/test_default_flow.py` | `hasattr` |
| `tests/integration/test_e2e_full_chain.py` | `hasattr` |

Matches the brief: tests may mention it as `hasattr` / similar negative assertions.

### `rootseeker-skill.yaml` in yaml files

**Hits in repo tree (excluding `repos/` / `.venv`):** none. No builtin leftovers.

(`skills/builtin/` is flat `SKILL.md` packages; no sidecar files.)

## Step 3 — Docs

Required:

- `docs/business-logic/04-skill-system.md` — parser only `SKILL.md`; three roots + overlay; PlaybookResolver; stepper deleted.
- `docs/business-logic/03-default-triage-flow.md` — default path AttemptRunner + playbook; 14 steps are playbook guidance, not YAML engine.
- `docs/business-logic/05-skill-runtime-flow-executor.md` — rewritten as “步进器已删除”; default path Agent playbook; `FLOW_STEP_UNSUPPORTED`.

Also corrected conflicting default-path sentences in: `00`, `01`, `02`, `06`, `08`, `09`, `10`. Did not invent new features (no DraftBuilder/Publisher on the default path).

## Step 4 — Spec status

After tests were green: `docs/superpowers/specs/2026-08-19-standard-skills-replace-flow-design.md` status → **已实现** (file was previously untracked; committed in `9bd8c3e`).

## Concerns

1. Production `rootseeker demo` without a configured LLM planner still fails (Case `SKILL_PLANNER_FAILED`). Tests stub the planner. This matches spec (no Flow fallback). Offline smoke now needs LLM or an injected planner.
2. Worker `--seed-demo` still returns 0 if the *task* completes even when the Case failed (TaskExecutor marks `CASE_RUN` completed regardless of case status). Pre-existing; not changed.
3. Other business-logic files (`07`, `12`, `14`, `16`, `18`) may still mention old Flow symbols in non-default-path sections. Required + listed MAY files were updated.
4. `SkillPublisher` / DraftBuilder can still write sidecar YAML; spec says they are not on the default execution path. Docs note this leftover.
5. Gitignored `repos/` still contains old `rootseeker-skill.yaml` copies; grep excluded that tree.

## Self-review

- Did not restore `execute_skill_flow`.
- Spec status flipped only after pytest exit 0.
- Two commits, no push, no amend.

## Branch-review fix

**HEAD before this fix:** `9bd8c3e4ceedc1048a4cf52cc96931f952d24289`  
**Date:** 2026-08-19  
**Status:** DONE

Fixed the two Important findings from `.superpowers/sdd/branch-review.md`. Did not restore YAML Flow. Did not expand into the Minor list except the webhook checkpoint `status` in the same handler (one-line, same defect).

### TDD — RED

New tests were written first and failed for the intended reasons (not typos):

| Test | Failure |
| --- | --- |
| `test_gateway_flow_run_reports_failed_when_planner_missing` | `status` was `"completed"` (hardcoded) |
| `test_flow_runtime_checkpoint_failed_when_planner_missing` | checkpoint `"status"` was `"completed"` |
| `test_task_executor_case_run_failed_when_planner_missing` / `_agent_...` | `TaskStatus.COMPLETED` |
| `test_webhook_ok_false_when_planner_missing` | `ok is True` |
| `test_set_role_writes_overlay_then_set_default_succeeds` | `PlaybookResolver` had no `set_role` |
| `test_gateway_server_registers_business_methods` | `skill.set_role` missing |
| `test_gateway_skill_set_role_then_set_default` | `GatewayMethodNotFoundError: skill.set_role` |
| `test_install_helper_set_role_then_set_default` | HTTP 405 on `POST /api/skills/{name}/role` |

### TDD — GREEN

Command:

```
uv run python -m pytest tests/unit/apps/test_admin_main.py tests/unit/gateway/test_gateway_business_methods.py tests/unit/task_runtime tests/unit/flow_runtime tests/unit/apps/test_api_webhook.py tests/unit/skill_system tests/unit/agent_runtime --tb=no
```

Exit **0**. **133 passed**, 1 pre-existing Starlette/`httpx` deprecation warning.

Ruff on touched Python files: only pre-existing `apps/api/main.py` I001/F401 (import order / unused `webhook_payload_to_case_create`); not introduced by this change.

### What changed

1. **Failure propagation:** `FlowExecutionResult.status` from `DefaultFlowRunResult.case.status`; gateway `flow.run`, flow checkpoint, CASE_RUN task (`COMPLETED` vs `FAILED`), webhook `ok` (HTTP 200 kept) all use Case / `AgentRunResult.status`.
2. **Overlay role:** `PlaybookResolver.set_role`; Admin `POST /api/skills/{name}/role`; Gateway `skill.set_role` (persist via `persist_skill_overlay`); Admin-web helper rows show 「标为排查流程」, playbooks keep 「设为默认」. SKILL.md is not rewritten. Builtin delete protection unchanged.

Did not push. Did not amend.
