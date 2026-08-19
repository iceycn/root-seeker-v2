# Task 7 Report: Migrate builtin skills to flat standard packages

**Branch:** `feat/standard-skills-replace-flow`  
**Commit:** `ca2b911` — feat(skill): flatten builtin skills into standard packages  
**Date:** 2026-08-19  
**Status:** DONE_WITH_CONCERNS

## Summary

Flattened `skills/builtin` from `flows/` + `tools/` prefixes into `skills/builtin/<name>/` standard packages. Deleted every `rootseeker-skill.yaml` sidecar. Rewrote each `SKILL.md` frontmatter so `name` equals the directory (kebab-case), `metadata.role` is `playbook` for `default-log-triage` and `helper` otherwise, and `allowed-tools` matches the task table verbatim. Playbook body includes the 14-step recommended order plus “call notify.send after the report”. Created `skills/custom/.gitkeep` and `skills/external/.gitkeep`. Set `DEFAULT_FLOW_SKILL_SLUG` and `skill_composer_default_flow` to `default-log-triage`. Replaced remaining `flows/default-log-triage` test/code identity strings (kept overlay/name-normalize inputs). Did not delete `execute_skill_flow` and did not switch `AttemptRunner`.

## TDD Evidence

### Step 1 — Write the failing test

Added `test_builtin_default_playbook_is_standard_package` to `tests/unit/skill_system/test_skill_registry.py` (verbatim from the brief). Left `test_discover_and_load_builtin_default_log_triage` skipped until after RED.

### Step 2 — RED

```
uv run python -m pytest tests/unit/skill_system/test_skill_registry.py::test_builtin_default_playbook_is_standard_package -q --tb=short
```

```
F                                                                        [100%]
E   rootseeker.skill_system.errors.SkillError: invalid skill name: 'Default log triage'
FAILED tests/unit/skill_system/test_skill_registry.py::test_builtin_default_playbook_is_standard_package
```

Failure is the expected missing-feature case: builtin packages still used Title Case names / old layout / sidecars, so `build_skill_registry` could not load `default-log-triage`.

### Step 3 — Migrate (`git mv`) then GREEN

Used `git mv` to flatten:

- `skills/builtin/flows/default-log-triage/` → `skills/builtin/default-log-triage/`
- `skills/builtin/tools/<name>/` → `skills/builtin/<name>/`

Then `git rm -f` all builtin `rootseeker-skill.yaml`. Removed empty `flows/` and `tools/` dirs. Rewrote frontmatter; kept helper bodies and `references/`.

Unskipped and rewrote `test_discover_and_load_builtin_default_log_triage` for the new package (`steps == []`, no sidecar, `role == playbook`).

```
uv run python -m pytest tests/unit/skill_system/test_skill_parser.py tests/unit/skill_system/test_skill_registry.py tests/unit/skill_system/test_skill_registry_roots.py -q --tb=short
```

```
...........                                                              [100%]
```

11 passed.

After slug replacement and related test updates:

```
uv run python -m pytest tests/unit/skill_system tests/unit/contracts/test_skill_contracts.py -q --tb=short
```

```
..................................................                       [100%]
```

50 passed. `uv run ruff check` on touched Python files: All checks passed.

## Files Changed

| File | Change |
| --- | --- |
| `skills/builtin/<name>/` | Flattened 11 packages; deleted sidecars; kebab `SKILL.md` frontmatter |
| `skills/custom/.gitkeep`, `skills/external/.gitkeep` | Empty roots for three-root discovery |
| `rootseeker/skill_system/registry.py` | `DEFAULT_FLOW_SKILL_SLUG = "default-log-triage"` |
| `rootseeker/infra_core/settings.py` | `skill_composer_default_flow = "default-log-triage"` |
| Production/script slug defaults | `evidence_expander`, `mcp_supplement`, `flow_runtime`, `flow_methods`, plugin.yaml, scripts |
| Tests | New playbook package test; rewritten builtin load test; slug strings; contracts without required steps |

## Self-Review

- Brief allowed-tools table written into frontmatter verbatim.
- Playbook body has 14 numbered steps and both “生成报告之后再调用 notify.send” and “call notify.send after the report”.
- Helper `references/` untouched except path (git mv).
- `execute_skill_flow` still exported from `rootseeker/skill_runtime/flow_executor.py`.
- `AttemptRunner` not switched.

## Concerns

- `load_skill_from_path` still defaults `skill_kind` to `FLOW` for every package. `SkillComposer.compose()` without `preferred_skill` can pick the alphabetically first builtin (e.g. `catalog-log-sources`) until Task 8 uses `PlaybookResolver`. Composer test now passes `preferred_skill`.
- `SkillPublisher` still writes `rootseeker-skill.yaml`; its unit test was updated to kebab-case `generated-test` so `load_skill_from_path` succeeds. Publisher rewrite is out of scope.
- `test_skill_names.py` and overlay payload in `test_skill_registry_roots.py` still use `flows/default-log-triage` as *input* to prove legacy-prefix normalization.

## Follow-up: skill_kind from metadata.role (2026-08-19)

Resolved the first concern: `load_skill_from_path` now sets `skill_kind` to `SkillKind.FLOW` when `metadata.role == "playbook"`, otherwise `SkillKind.TOOL`. `SkillComposer.list_by_kind(FLOW)` no longer treats helpers as flows.

### TDD

RED (`helper.skill_kind` was `FLOW`, expected `TOOL`):

```
uv run python -m pytest tests/unit/skill_system/test_skill_parser.py::test_load_skill_kind_from_metadata_role tests/unit/skill_system/test_skill_registry.py::test_builtin_helper_is_tool_and_playbook_is_flow -q --tb=short
```

```
FF
AssertionError: assert <SkillKind.FLOW: 'flow'> == <SkillKind.TOOL: 'tool'>
```

GREEN covering tests:

```
uv run python -m pytest tests/unit/skill_system/test_skill_parser.py tests/unit/skill_system/test_skill_registry.py -q --tb=short
```

```
........                                                                 [100%]
```

8 passed. Added `test_load_skill_kind_from_metadata_role` and `test_builtin_helper_is_tool_and_playbook_is_flow` (`code-lookup` → tool, `default-log-triage` → flow).

