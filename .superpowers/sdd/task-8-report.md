# Task 8 Report: Agent becomes the only default executor (remove Flow fallback)

**Branch:** `feat/standard-skills-replace-flow`  
**Commit:** `121b04f` — feat(agent): make AttemptRunner the only default executor  
**Date:** 2026-08-19  
**Status:** DONE_WITH_CONCERNS

## Summary

Default Case execution no longer falls back to the YAML flow stepper. `AttemptRunner.run_once` always resolves a playbook via `PlaybookResolver`, loads playbook env into a per-run MCP `extra_env` merge (then restores), injects playbook body + skill catalog (name+description only) into planner messages, and fails with `SKILL_PLANNER_FAILED` / `SKILL_TOOL_NOT_ALLOWED` / `SKILL_ENV_MISSING` instead of calling `flow_runtime.run_default` / `execute_skill_flow`. `DevRuntime.run_default_flow_from_case_request` now delegates to `run_agent_from_case_request`. `create_dev_runtime` scans three skill roots via `build_skill_registry`. `execute_skill_flow` and the default_log_triage_flow plugin were not deleted (Task 9).

## TDD Evidence

### Step 1 — Write the failing tests

Added `tests/unit/agent_runtime/test_playbook_attempt.py` with the brief snippets (second test filled in: failing planner stub, `run_once(allow_default_fallback=False)`, assert flow not called, `status == "failed"`, `error_code == SKILL_PLANNER_FAILED`) plus focused coverage for `SKILL_TOOL_NOT_ALLOWED` (disallowed tool is not executed) and `SKILL_ENV_MISSING` (planner is not called).

### Step 2 — RED

```
uv run python -m pytest tests/unit/agent_runtime/test_playbook_attempt.py -q --tb=short
```

```
FFFF                                                                     [100%]
TypeError: build_tool_planner_messages() got an unexpected keyword argument 'playbook_text'
AssertionError: assert None == 'SKILL_PLANNER_FAILED'
AssertionError: assert ['shell.exec'] == []
assert 1 == 0  (planner.calls)
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_planner_messages_include_playbook_not_unloaded_helper_body
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_attempt_runner_does_not_call_execute_skill_flow
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_disallowed_tool_fails_without_executing
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_missing_playbook_env_fails_without_planning
```

Failures match missing behavior: new planner-message kwargs, no `error_code` on planner failure, disallowed tools still executed, env not checked before planning.

### Step 3 — Implement, then GREEN

```
uv run python -m pytest tests/unit/agent_runtime/test_playbook_attempt.py -q --tb=short
```

```
....                                                                     [100%]
```

4 passed.

Before commit:

```
uv run python -m pytest tests/unit/agent_runtime -q --tb=short
```

```
.................                                                        [100%]
```

17 passed. `uv run ruff check` on touched Python files: All checks passed (import order auto-fixed).

## Files Changed

| File | Change |
| --- | --- |
| `rootseeker/agent_runtime/llm_tool_planner.py` | `build_tool_planner_messages` / `plan()` take `playbook_text=""`, `skill_catalog=None`, `allowed_tool_names=None` |
| `rootseeker/agent_runtime/attempt_runner.py` | Remove Flow fallback; PlaybookResolver; env merge; allowed-tools filter; error_code on failed Attempts |
| `rootseeker/bootstrap/runtime.py` | `run_default_flow_from_case_request` → Agent; `create_dev_runtime` uses `build_skill_registry` |
| `tests/unit/agent_runtime/test_playbook_attempt.py` | New TDD tests |
| `tests/unit/agent_runtime/test_agent_runtime.py` | Payload tests inject stub planner; drop Flow-fallback assertions |

`prompt_builder.py` was listed in the brief but left unchanged: playbook/catalog/allowed-tools go through `build_tool_planner_messages` only (no second injection path). Secrets never enter substitutions, so they are not in `AttemptResult.prompt_messages`.

## Self-Review

- `allow_default_fallback` default is `False`; the parameter is ignored so even `True` does not call `flow_runtime.run_default` / `execute_skill_flow`.
- Failed Attempt metadata includes `error_code`.
- Allowed tools at start = playbook `bound_tools`; plan tools outside that set fail without `execute_records`.
- Skill catalog is name+description only; helper `SKILL.md` bodies are not loaded into planner messages.
- Overlay constructed as `overlay=None` (Task 10 persists Admin overlay).
- Did not delete `execute_skill_flow` or the default_log_triage_flow plugin.

## Concerns

- **No LLM planner ⇒ default Case path fails.** `run_default_flow_from_case_request` now always goes through Agent. With LLM disabled and no injected planner, the result is `SKILL_PLANNER_FAILED` rather than a completed YAML flow. Integration / bootstrap / API tests that still expect 14-step Flow completion will fail until Task 9 restubs them.
- **Admin overlay not applied at run time.** `PlaybookResolver(..., overlay=None)` until Task 10; disable/set-default from Admin settings does not yet affect the default executor.
- **`set_extra_env` restores after each attempt** and closes MCP sessions (existing `McpServerManager` behavior). Correct for leak prevention; may restart stdio sessions more often.
- **`publish_completion=False` is ignored** on `run_default_flow_from_case_request` because `run_agent_from_case_request` always publishes.

## Fix round

Important review findings from `.superpowers/sdd/task-8-review.md` (env overlay, helper allow-list union, playbook WRITE tools / `notify_skipped`). Did not delete `execute_skill_flow` and did not persist Admin overlay.

### TDD RED

```
uv run python -m pytest tests/unit/mcp_plane/test_server_manager.py::test_run_env_overlay_survives_provider_refresh_and_skill_key_wins tests/unit/agent_runtime/test_playbook_attempt.py::test_skill_env_overlay_survives_provider_refresh_during_plan tests/unit/agent_runtime/test_playbook_attempt.py::test_loaded_helper_bound_tools_are_unioned_into_allow_list tests/unit/agent_runtime/test_playbook_attempt.py::test_playbook_write_tools_reach_planner_and_omitted_notify_is_skipped -q --tb=line
```

```
FFFF                                                                     [100%]
AttributeError: 'McpServerManager' object has no attribute 'set_run_env_overlay'
AssertionError: assert None == 'secret'
AssertionError: assert 'graph.cypher' in []
AssertionError: assert 'notify.send' in ['incident.normalize']
FAILED tests/unit/mcp_plane/test_server_manager.py::test_run_env_overlay_survives_provider_refresh_and_skill_key_wins
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_skill_env_overlay_survives_provider_refresh_during_plan
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_loaded_helper_bound_tools_are_unioned_into_allow_list
FAILED tests/unit/agent_runtime/test_playbook_attempt.py::test_playbook_write_tools_reach_planner_and_omitted_notify_is_skipped
```

Failures match the three Important bugs: provider refresh dropped skill keys; helper-only `graph.cypher` stayed disallowed; WRITE `notify.send` never reached the planner.

### TDD GREEN

Implemented: `McpServerManager.set_run_env_overlay` merged on top of provider output; `AttemptRunner` sets overlay for the run and restores extra_env + provider in `finally`; `_allowed_tools_for_run(playbook, loaded_helpers)`; planner tools use the playbook/helper allow-list (do not strip listed WRITE tools); omitted `notify.send` sets `notify_skipped` on attempt and report metadata.

```
uv run python -m pytest tests/unit/agent_runtime/test_playbook_attempt.py tests/unit/mcp_plane/test_server_manager.py tests/unit/agent_runtime -q --tb=short
```

```
........................                                                 [100%]
```

24 passed. `uv run ruff check` on touched Python files: All checks passed (import wrap auto-fixed in `test_server_manager.py`).
