# Message Notification Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Admin message templates (system + custom), fillable notify variables, and per-channel template selection so outbound notifications render from templates instead of hard-coded text.

**Architecture:** Independent `MessageTemplateStore` (file/sqlite/mysql following storage backend) holds system + custom templates. `build_notify_context` builds variable maps from Case/Report. A tiny `{{var}}` / `{{#var}}` renderer fills bodies. Broadcast dispatch resolves each channel's `template_id` (fallback `system-default`) and sends per-channel rendered text.

**Tech Stack:** Python 3 / pytest, existing Admin FastAPI + React admin-web (Ant Design), existing NotificationChannelStore patterns.

**Spec:** `docs/superpowers/specs/2026-09-09-message-notification-templates-design.md`

## Global Constraints

- Do not add Mustache/Jinja dependencies; keep a minimal custom renderer.
- System template id is exactly `system-default`; `kind=system` cannot be deleted; user creates only `kind=custom`.
- Empty channel `template_id` falls back to system template at send time.
- Preserve existing notify test semantics (readable card, skip procedural narrative, resolve service name).
- Do not commit unless the user explicitly asks (local plan steps may stage files only).
- Branch: `v1.1.1`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `rootseeker/channel_routing/message_template_render.py` | Render `{{var}}` and `{{#var}}...{{/var}}` |
| `rootseeker/channel_routing/notify_variables.py` | Variable catalog metadata + `build_notify_context` |
| `rootseeker/storage/message_templates.py` | Template store (file/sqlite/mysql) + ensure system template |
| `rootseeker/storage/backend_resolve.py` | `resolve_message_template_store` |
| `rootseeker/storage/notification_channels.py` | Add `template_id` on channel payload |
| `rootseeker/channel_routing/notify_config.py` | Pass `template_id` / `channel_id` in outbound metadata |
| `rootseeker/channel_routing/notify_dispatch.py` | Per-channel render + send |
| `rootseeker/skill_runtime/rule_step_argument_resolver.py` | Delegate message build to context + system template render (compat) |
| `apps/admin/main.py` | Message-template APIs; channel `template_id` |
| `apps/admin-web/src/App.tsx` | 消息模板 menu + channel template select |

---

### Task 1: Template renderer

**Files:**
- Create: `rootseeker/channel_routing/message_template_render.py`
- Test: `tests/unit/channel_routing/test_message_template_render.py`

**Interfaces:**
- Produces: `render_message_template(body: str, context: dict[str, str]) -> str`
- Produces: `_is_truthy(value: str) -> bool` (internal ok)

- [ ] **Step 1: Write the failing test**

```python
from rootseeker.channel_routing.message_template_render import render_message_template


def test_replaces_variables() -> None:
    assert render_message_template("Hi {{name}}", {"name": "Ada"}) == "Hi Ada"


def test_conditional_block_omits_when_empty() -> None:
    body = "A\n{{#service}}服务：{{service}}\n{{/service}}B"
    assert render_message_template(body, {"service": ""}) == "A\nB"
    assert render_message_template(body, {"service": "api"}) == "A\n服务：api\nB"


def test_unknown_variable_becomes_empty() -> None:
    assert render_message_template("x{{missing}}y", {}) == "xy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/channel_routing/test_message_template_render.py -v`  
Expected: FAIL import or missing symbol

- [ ] **Step 3: Write minimal implementation**

```python
"""Minimal Mustache-like renderer for notify message templates."""
from __future__ import annotations
import re

__all__ = ["render_message_template"]

_COND = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.DOTALL)
_VAR = re.compile(r"\{\{(\w+)\}\}")


def render_message_template(body: str, context: dict[str, str]) -> str:
    def repl_cond(match: re.Match[str]) -> str:
        key = match.group(1)
        inner = match.group(2)
        value = str(context.get(key, "") or "")
        if not value.strip():
            return ""
        return render_message_template(inner, context)

    text = _COND.sub(repl_cond, body)

    def repl_var(match: re.Match[str]) -> str:
        return str(context.get(match.group(1), "") or "")

    return _VAR.sub(repl_var, text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/channel_routing/test_message_template_render.py -v`  
Expected: PASS

---

### Task 2: Notify context + variable catalog

**Files:**
- Create: `rootseeker/channel_routing/notify_variables.py`
- Modify: `rootseeker/skill_runtime/rule_step_argument_resolver.py` (move/reuse helpers; `build_notify_args` uses context + default body render)
- Test: extend `tests/unit/skill_system/test_skill_driven_flow.py` (keep existing asserts) + `tests/unit/channel_routing/test_notify_variables.py`

**Interfaces:**
- Consumes: `render_message_template`, CaseCreateRequest, CaseReport
- Produces:
  - `NOTIFY_VARIABLES: list[dict[str, str]]` with `name` + `description`
  - `SYSTEM_DEFAULT_TEMPLATE_BODY: str`
  - `build_notify_context(*, case_request, report) -> dict[str, str]`
  - `render_notify_message(*, case_request, report, body: str | None = None) -> str`

- [ ] **Step 1: Write failing tests for context keys and default render parity**

```python
from rootseeker.channel_routing.notify_variables import (
    SYSTEM_DEFAULT_TEMPLATE_BODY,
    build_notify_context,
    render_notify_message,
)
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.evidence import RootCauseConclusion
from rootseeker.contracts.report import CaseReport


def test_build_notify_context_exposes_catalog_keys() -> None:
    ctx = build_notify_context(
        case_request=CaseCreateRequest(
            title="错误排查请求",
            symptom="java.lang.NullPointerException: boom\n\tat com.x.A.run(A.java:1)\n",
            service_name="demo-api",
            source="admin-error-chat",
        ),
        report=CaseReport(
            case_id="case-1",
            title="t",
            summary="s",
            evidence_item_ids=[],
            root_cause=RootCauseConclusion(
                title="NullPointerException",
                narrative="空指针",
                confidence=0.5,
            ),
        ),
    )
    for key in ("headline", "problem", "service", "cause", "narrative", "confidence", "case_id", "title", "exception", "symptom"):
        assert key in ctx
    assert ctx["case_id"] == "case-1"
    assert ctx["confidence"] == "50%"


def test_default_template_includes_brand_and_case() -> None:
    msg = render_notify_message(
        case_request=CaseCreateRequest(
            title="错误排查请求",
            symptom="java.lang.IllegalStateException: boom\n\tat com.example.A.run(A.java:1)\n",
            service_name="demo-api",
            source="admin-error-chat",
        ),
        report=CaseReport(case_id="case-proc", title="t", summary="s", evidence_item_ids=[]),
        body=SYSTEM_DEFAULT_TEMPLATE_BODY,
    )
    assert "【RootSeeker】" in msg
    assert "case-proc" in msg
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/channel_routing/test_notify_variables.py -v`

- [ ] **Step 3: Implement `notify_variables.py` by extracting logic from `_build_notify_message`**

Move cleaning helpers as needed; `build_notify_context` returns all catalog keys as strings; empty string when absent. `confidence` formatted as `f"{int(round(c*100))}%"` only when `c > 0`, else `""`. `symptom` truncated to 500 chars. `render_notify_message` calls `render_message_template(body or SYSTEM_DEFAULT_TEMPLATE_BODY, context)`.

Update `build_notify_args` to:

```python
def build_notify_args(*, case_request, report):
    channel = case_request.metadata.get("notify_channel", "webhook")
    return {
        "channel": channel,
        "message": render_notify_message(case_request=case_request, report=report),
        "context": build_notify_context(case_request=case_request, report=report),
    }
```

- [ ] **Step 4: Run existing notify formatting tests + new tests**

Run: `pytest tests/unit/skill_system/test_skill_driven_flow.py -k build_notify_args -v tests/unit/channel_routing/test_notify_variables.py -v`  
Expected: PASS (adjust SYSTEM_DEFAULT_TEMPLATE_BODY / context cleaning until parity)

---

### Task 3: MessageTemplateStore

**Files:**
- Create: `rootseeker/storage/message_templates.py`
- Modify: `rootseeker/storage/backend_resolve.py` — add `resolve_message_template_store`
- Test: `tests/unit/storage/test_message_template_store.py`

**Interfaces:**
- Produces: `SYSTEM_TEMPLATE_ID = "system-default"`
- Produces: `build_message_template_store(repo_root, settings=...) -> MessageTemplateStore`
- Protocol methods: `list_templates`, `get_template`, `upsert_template`, `delete_template`
- `ensure_system_template()` on load/build

- [ ] **Step 1: Failing tests**

```python
def test_store_ensures_system_template(tmp_path):
    store = FileMessageTemplateStore(tmp_path / "t.json")
    items = store.list_templates()
    assert any(t["template_id"] == "system-default" and t["kind"] == "system" for t in items)


def test_cannot_delete_system_template(tmp_path):
    store = FileMessageTemplateStore(tmp_path / "t.json")
    with pytest.raises(ValueError, match="system"):
        store.delete_template("system-default")


def test_custom_template_crud(tmp_path):
    store = FileMessageTemplateStore(tmp_path / "t.json")
    saved = store.upsert_template({"name": "简短", "body": "Case：{{case_id}}", "kind": "custom"})
    assert saved["kind"] == "custom"
    store.delete_template(saved["template_id"])
    assert store.get_template(saved["template_id"]) is None
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement store mirroring `notification_channels.py` patterns** (File + Sqlite + Mysql + builder). Force `kind=custom` when creating without system id. Updating `system-default` may change name/body/description but not kind/id. Reject delete of system.

- [ ] **Step 4: Run — PASS**

---

### Task 4: Channel `template_id` + per-channel dispatch

**Files:**
- Modify: `rootseeker/storage/notification_channels.py` — normalize `template_id`
- Modify: `rootseeker/channel_routing/notify_config.py` — put `template_id`, `channel_id` into `OutboundTarget.metadata`
- Modify: `rootseeker/channel_routing/notify_dispatch.py` — accept optional `context: dict[str, str] | None`; when provided, render per target
- Modify: call sites that broadcast (attempt_runner / adapters) to pass context when available
- Test: `tests/unit/channel_routing/test_notify_broadcast.py` (extend)

**Interfaces:**
- Consumes: `build_message_template_store`, `render_message_template`, `SYSTEM_TEMPLATE_ID`
- Produces: `dispatch_broadcast_notify(message, *, channel, context=None, ...)`

- [ ] **Step 1: Failing test — two channels different templates yield different messages**

Use monkeypatch/stub registry capturing sent messages; create file stores under tmp_path; set two enabled channels with different `template_id`; call dispatch with context `{"case_id":"c1", ...}`; assert two different bodies.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Resolution helper:

```python
def resolve_template_body(template_store, template_id: str) -> str:
    tid = (template_id or "").strip() or SYSTEM_TEMPLATE_ID
    record = template_store.get_template(tid) or template_store.get_template(SYSTEM_TEMPLATE_ID)
    return str((record or {}).get("body") or SYSTEM_DEFAULT_TEMPLATE_BODY)
```

In broadcast loop: if `context` is not None, `message = render_message_template(resolve_template_body(...), context)` else use provided `message` (env fallback path unchanged).

- [ ] **Step 4: Run broadcast + channel store tests — PASS**

---

### Task 5: Admin API

**Files:**
- Modify: `apps/admin/main.py`
- Test: existing admin API tests pattern (add cases in `tests/` wherever notification-channel API tests live)

**Interfaces:**
- `GET/POST /api/message-templates`, `GET/PUT/DELETE /api/message-templates/{template_id}`
- Channel create/update/patch accept `template_id`
- List templates response includes `variables` from `NOTIFY_VARIABLES`
- Test-send uses sample context + channel template

- [ ] **Step 1: Write API tests (create custom, forbid delete system, channel template_id roundtrip)**

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Wire store + pydantic models + routes (mirror notification-channels)**

- [ ] **Step 4: Run — PASS**

---

### Task 6: Admin Web UI

**Files:**
- Modify: `apps/admin-web/src/App.tsx`

**Interfaces:**
- Route `/message-templates`, menu label `消息模板`
- Page: table + create/edit modal; show variable catalog; hide delete for system
- Channel form: Select for `template_id`

- [ ] **Step 1: Add types, route maps, menu item, load/save handlers parallel to notificationChannels**

- [ ] **Step 2: Add message-templates view (table + modal with body TextArea + variables Alert/Table)**

- [ ] **Step 3: Extend channel form with template Select (`允许空 = 默认系统模板`)**

- [ ] **Step 4: Manual smoke — `npm`/`pnpm` build or typecheck if available; fix TS errors**

---

### Task 7: Verification gate

- [ ] **Step 1: Run focused suite**

```bash
pytest tests/unit/channel_routing/test_message_template_render.py tests/unit/channel_routing/test_notify_variables.py tests/unit/storage/test_message_template_store.py tests/unit/channel_routing/test_notify_broadcast.py tests/unit/skill_system/test_skill_driven_flow.py -k "notify or build_notify or message_template" -v
```

- [ ] **Step 2: Fix any regressions**

- [ ] **Step 3: Spec coverage checklist**

1. 消息模板菜单 — Task 6  
2. 可用变量 — Task 2 + 5/6  
3. 渠道选模板并按模板发送 — Task 4–6  
4. 系统模板可改不可删 / 普通可增删改 — Task 3–6  

---

## Spec coverage self-check

| Spec requirement | Task |
| --- | --- |
| Renderer `{{var}}` + conditionals | 1 |
| Variable catalog + context | 2 |
| System template ensure + delete guard | 3 |
| Channel template_id + per-channel send | 4 |
| Admin API + variables in list | 5 |
| Admin menus/UI | 6 |
| Fallback / deleted template | 4 resolve helper |
| Test channel uses template | 5 |

## Placeholder scan

None intentional; commit steps deferred to user request.
