# Task 3 Report: Three-root SkillRegistry + overlay

**Branch:** `feat/standard-skills-replace-flow`  
**Commit:** `60a7d59` — feat(skill): three-root SkillRegistry with overlay  
**Date:** 2026-08-19

## Summary

Implemented three-root skill discovery and registry building with admin overlay support:

- `discover_skill_files(root)` — unchanged rglob `SKILL.md` behavior; parameter renamed to `root`
- `SkillOverlayState`, `normalize_overlay_payload`, `apply_overlay` — overlay state with legacy slug normalization
- `build_skill_registry(builtin_root, custom_root, external_root, overlay)` — scans three roots with correct `SkillSourceKind`, builtin names protected from later-root overwrite, custom/external same-name uses upsert (later wins)
- `SkillRegistry.get(name)` — lookup via `normalize_skill_name`
- `build_registry_from_builtin_skills` — thin wrapper delegating to `build_skill_registry`

Did not migrate `skills/builtin`. Did not implement PlaybookResolver (Task 4).

## TDD Evidence

### Step 1 — Write failing test

Created `tests/unit/skill_system/test_skill_registry_roots.py` verbatim from task brief:
- `test_build_skill_registry_scans_three_roots_and_applies_overlay`

### Step 2 — RED

**Command:**

```text
uv run python -m pytest tests/unit/skill_system/test_skill_registry_roots.py -q --tb=short
```

**Output:**

```text
ERROR collecting tests/unit/skill_system/test_skill_registry_roots.py
ImportError: No module named 'rootseeker.skill_system.overlay'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

### Step 3 — Implementation

**`rootseeker/skill_system/overlay.py`** (new)
- `SkillOverlayState` dataclass with `default_playbook` and `overlays`
- `normalize_overlay_payload` — normalizes `default_playbook` and overlay keys via `normalize_skill_name`
- `apply_overlay` — writes `metadata.enabled` and `metadata.role` from overlay entry when present

**`rootseeker/skill_system/registry.py`**
- `SkillRegistry.get` uses `normalize_skill_name(slug)`
- `build_skill_registry` — builtin `register`, custom/external `upsert`, skip names already in builtin set, then apply overlay to all specs
- `build_registry_from_builtin_skills` — delegates to `build_skill_registry` with `custom_root=builtin.parent/"custom"`, `external_root=builtin.parent/"external"`

**`rootseeker/skill_system/discovery.py`**
- Renamed parameter `builtin_skills_root` → `root` (interface per brief)

### Step 4 — GREEN

**Command:**

```text
uv run python -m pytest tests/unit/skill_system/test_skill_registry_roots.py -q --tb=short
```

**Output:**

```text
.                                                                        [100%]
1 passed
```

## Files Changed

| File | Change |
|------|--------|
| `rootseeker/skill_system/overlay.py` | Created — overlay state and apply/normalize helpers |
| `rootseeker/skill_system/registry.py` | `build_skill_registry`, `get` normalization, thin builtin wrapper |
| `rootseeker/skill_system/discovery.py` | Parameter rename `root` |
| `tests/unit/skill_system/test_skill_registry_roots.py` | Created — three-root + overlay integration test |

## Self-Review

- **Brief compliance:** Test copied exactly; overlay core matches brief snippet; `build_skill_registry` registers BUILTIN/CUSTOM/EXTERNAL, protects builtin names, applies overlay post-registration.
- **No weakening:** Builtin names cannot be overwritten by custom/external; overlay only mutates metadata fields explicitly present in overlay entry.
- **Scope:** No builtin migration; no PlaybookResolver; `build_registry_from_builtin_skills` remains thin wrapper.
- **Residual risk:** `build_registry_from_builtin_skills` still fails on unmigrated `skills/builtin/*` (Task 7); pre-existing failures in `test_skill_driven_flow.py` and `test_skill_publisher.py` unchanged.

## Concerns

- `get_default_log_triage_skill` still uses `DEFAULT_FLOW_SKILL_SLUG = "flows/default-log-triage"` while registry keys are now normalized kebab names — will need alignment when builtin skills are migrated (Task 7) or when PlaybookResolver (Task 4) wires default resolution.
- `overlay.py` not yet exported from `rootseeker.skill_system.__init__` — acceptable until Task 8 wires `create_dev_runtime`.

## Review Fix (Important)

**Commit:** `8872337` — fix(skill): normalize SkillRegistry index keys  
**Date:** 2026-08-19

### Findings addressed

1. Added tests: custom/external skip builtin names; external upserts over custom; `SkillRegistry` indexes by `normalize_skill_name`.
2. `SkillRegistry.register` / `upsert` / `unregister` now index by normalized key, matching `get()`; duplicate detection uses normalized key.

### TDD — RED

**Command:**

```text
uv run python -m pytest tests/unit/skill_system/test_skill_registry_roots.py -q --tb=short
```

**Output:**

```text
...FF                                                                    [100%]
FAILED test_skill_registry_indexes_by_normalized_slug
FAILED test_skill_registry_register_rejects_duplicate_normalized_slug
```

### TDD — GREEN

**Command:**

```text
uv run python -m pytest tests/unit/skill_system/test_skill_registry_roots.py -q --tb=short
```

**Output:**

```text
.....                                                                    [100%]
5 passed
```

