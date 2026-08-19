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

- `require=False` path not covered by brief tests; behavior implemented per spec but untested here
- Optional keys with values are included in `mcp_extra` when resolved but do not affect `missing` list
