# Task 5 Report: SkillEnvResolver

**Branch:** `feat/standard-skills-replace-flow`  
**Commit:** `d31ed17` — feat(skill): add SkillEnvResolver with env priority and secret handling  
**Date:** 2026-08-19  
**Status:** DONE

## Summary

Implemented `SkillEnvResolver` in `rootseeker/skill_system/env_resolver.py`:

- `SkillEnvResolution(mcp_extra, substitutions, missing)` — frozen dataclass for resolved env state
- `resolve_skill_env(*, declared_keys, optional_keys, process_env, admin_items, require=True)` — merges env with priority `process_env < Admin runtime < Admin skill`
- `substitute_non_secret(text, substitutions)` — replaces `${KEY}` placeholders for non-secret values
- `scope=mcp` admin items ignored (not included in `mcp_extra` or substitutions)
- Undeclared `scope=skill` keys excluded from output
- `secret=True` values go to `mcp_extra` but not `substitutions`
- `require=True` (default) raises `SkillError("SKILL_ENV_MISSING", ...)` for missing required keys; `require=False` populates `missing` only

Did not wire AttemptRunner (Task 8). Did not implement installer (Task 6).

## TDD Evidence

### Step 1 — Write failing tests

Created `tests/unit/skill_system/test_skill_env_resolver.py` with exact cases from brief:

- `test_priority_skill_overrides_runtime_and_process`
- `test_secret_not_in_substitutions`
- `test_undeclared_skill_scope_not_included`
- `test_missing_required_raises`

### Step 2 — Verify RED

```
uv run python -m pytest tests/unit/skill_system/test_skill_env_resolver.py -q --tb=short
```

```
ERROR tests/unit/skill_system/test_skill_env_resolver.py
ModuleNotFoundError: No module named 'rootseeker.skill_system.env_resolver'
```

### Step 3 — Implement resolver

Added `env_resolver.py` with priority merge, mcp scope filtering, secret exclusion from substitutions, and `substitute_non_secret`.

### Step 4 — Verify GREEN

```
uv run python -m pytest tests/unit/skill_system/test_skill_env_resolver.py -q --tb=short
```

```
....                                                                     [100%]
4 passed
```

## Concerns

- Addressed in Review Fix: `require=False` and overlapping declared+optional keys are now tested; `missing` excludes `optional_keys`.

## Review Fix (Important)

**Commit:** `4a938bc` — fix(skill): treat overlapping declared env keys as optional  
**Date:** 2026-08-19  
**Status:** DONE (review findings)

### Findings addressed

1. Keys in both `declared_keys` and `optional_keys` are optional: `missing` excludes `optional_keys`, so a missing overlap does not raise `SKILL_ENV_MISSING`.
2. Tests added:
   - `test_overlapping_declared_optional_missing_does_not_raise`
   - `test_mcp_scope_item_is_ignored`
   - `test_require_false_records_missing_without_raising`

### TDD — RED

```
uv run python -m pytest tests/unit/skill_system/test_skill_env_resolver.py -q --tb=short
```

```
....F..                                                                  [100%]
================================== FAILURES ===================================
__________ test_overlapping_declared_optional_missing_does_not_raise __________
tests\unit\skill_system\test_skill_env_resolver.py:53: in test_overlapping_declared_optional_missing_does_not_raise
    result = resolve_skill_env(
rootseeker\skill_system\env_resolver.py:87: in resolve_skill_env
    raise SkillError(
E   rootseeker.skill_system.errors.SkillError: Missing required env keys: OVERLAP
=========================== short test summary info ===========================
FAILED tests/unit/skill_system/test_skill_env_resolver.py::test_overlapping_declared_optional_missing_does_not_raise
```

(`test_mcp_scope_item_is_ignored` and `test_require_false_records_missing_without_raising` already passed.)

### TDD — GREEN

`missing` now: `[key for key in declared_keys if key not in mcp_extra and key not in set(optional_keys)]`

```
uv run python -m pytest tests/unit/skill_system/test_skill_env_resolver.py -q --tb=short
```

```
.......                                                                  [100%]
```

Exit code 0 (7 passed).
