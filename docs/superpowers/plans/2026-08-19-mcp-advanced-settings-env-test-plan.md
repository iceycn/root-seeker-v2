# MCP Advanced-Settings Env Injection Test Plan

> **For agentic workers:** 本文件是**验证计划**（代码已实现）。按 Task 顺序执行命令；每步以 pytest 输出为证据，禁止凭记忆声称通过。

**Goal:** 证明高级设置中的环境变量会注入 MCP stdio 子进程，且作用域 / 覆盖优先级 / 热更新行为符合设计。

**Architecture:** Admin `env_vars`（scope=`runtime`/`mcp`）经 `env_from_admin_items` 进入 `McpServerManager.extra_env`；spawn 时 `merge_stdio_env(extra_env, server_env)` 后交给 `McpStdioSession`。Server JSON `env` 覆盖同名高级设置变量。`extra_env_provider` 在下次 invoke 时重读配置并重启会话。

**Tech Stack:** pytest、stdio MCP fixture `tests/fixtures/mcp_echo_server.py`（`echo` / `echo_env`）、FastAPI TestClient、`create_dev_runtime`。

## Global Constraints

- 语言：简体中文说明；命令与断言用英文标识符。
- 不 commit / push。
- 每个 Task 必须跑指定 pytest 命令并记录 exit code。
- 作用域：`runtime`/`mcp` 注入 MCP；`skill` 不注入。
- 优先级：高级设置 extra_env < MCP Server JSON `env`。
- 禁止把密钥写进 git；测试值用 `from-admin` / `secret-from-advanced` 这类假值。

---

## File Structure

| 文件 | 责任 |
| --- | --- |
| `rootseeker/mcp_plane/process_env.py` | 从 Admin items 筛选 scope，合并 extra_env 与 server env |
| `rootseeker/mcp_plane/server_manager.py` | spawn/invoke 传入 extra_env；provider 变更时关会话 |
| `rootseeker/mcp_plane/stdio_session.py` | 把 env 写入 MCP 子进程 |
| `rootseeker/bootstrap/runtime.py` | `mcp_extra_env` 为空时从 AdminConfigStore 加载 |
| `apps/admin/config_store.py` | `mcp_runtime_env()` / `upsert_env_var` |
| `apps/admin/main.py` | POST/DELETE `/api/env-vars` 后 `set_extra_env` |
| `apps/api/main.py` | 启动时注入 extra_env + provider |
| `tests/fixtures/mcp_echo_server.py` | `echo_env` 返回 `os.environ[key]` |
| `tests/unit/mcp_plane/test_process_env.py` | 筛选、合并、stdio 可见性 |
| `tests/unit/mcp_plane/test_server_manager.py` | invoke 注入与 provider 热更新 |
| `tests/unit/apps/test_admin_main.py` | Admin API → manager.extra_env |
| `tests/unit/test_bootstrap_storage.py` | create_dev_runtime 自动加载 Admin env |

## Coverage Matrix

| ID | 场景 | 期望 | 测试 |
| --- | --- | --- | --- |
| T1 | scope runtime + mcp | 进入 extra_env | `test_env_from_admin_items_keeps_runtime_and_mcp_scopes` |
| T2 | scope skill / 空 key | 被丢弃 | 同上 |
| T3 | 缺省 scope | 视为 runtime | `test_env_from_admin_items_defaults_missing_scope_to_runtime` |
| T4 | Server JSON 覆盖 | 同名键用 server 值 | `test_merge_stdio_env_server_json_overrides_admin` + stdio 实跑 |
| T5 | stdio 子进程读到 extra_env | `echo_env` 返回注入值 | `test_stdio_session_sees_injected_env` |
| T6 | Manager.invoke 带 extra_env | 子进程读到 `from-admin` | `test_mcp_stdio_invoke_uses_admin_extra_env` |
| T7 | provider 改值后再次 invoke | 新进程读到新值 | `test_mcp_extra_env_provider_restarts_session_on_change` |
| T8 | Admin POST runtime 变量 | `app.state.runtime.mcp_server_manager.extra_env` 含该键 | `test_upsert_env_var_injects_runtime_scope_into_mcp_manager` |
| T9 | Admin POST skill 变量 | extra_env 不含该键 | 同上 |
| T10 | `create_dev_runtime` 未显式传 extra_env | 从 Admin config 加载 runtime 变量 | `test_create_dev_runtime_loads_admin_advanced_settings_env` |
| T11 | 回归 | mcp_plane / agent_runtime / admin_main 全绿 | 目录级 pytest |

---

### Task 1: 作用域筛选与合并（纯函数）

**Files:**
- Test: `tests/unit/mcp_plane/test_process_env.py`
- Code: `rootseeker/mcp_plane/process_env.py`

**Interfaces:**
- Consumes: `env_from_admin_items(items: list[dict] | None) -> dict[str, str]`
- Consumes: `merge_stdio_env(*, extra_env, server_env) -> dict[str, str]`
- Produces: T1–T4 纯函数证据

- [x] **Step 1: 跑筛选与合并测试**

Run:

```bash
uv run python -m pytest tests/unit/mcp_plane/test_process_env.py::test_env_from_admin_items_keeps_runtime_and_mcp_scopes tests/unit/mcp_plane/test_process_env.py::test_env_from_admin_items_defaults_missing_scope_to_runtime tests/unit/mcp_plane/test_process_env.py::test_merge_stdio_env_server_json_overrides_admin -q --tb=short
```

Expected: 3 passed, exit 0

---

### Task 2: stdio 子进程真正读到环境变量

**Files:**
- Test: `tests/unit/mcp_plane/test_process_env.py`
- Fixture: `tests/fixtures/mcp_echo_server.py`
- Code: `rootseeker/mcp_plane/stdio_session.py`

**Interfaces:**
- Consumes: `McpStdioSession(command, args, env=...).call_tool("echo_env", {"key": ...})`
- Produces: `result["text"]` 等于注入值

- [x] **Step 1: 跑 stdio 注入测试**

Run:

```bash
uv run python -m pytest tests/unit/mcp_plane/test_process_env.py::test_stdio_session_sees_injected_env tests/unit/mcp_plane/test_process_env.py::test_discover_stdio_tools_lists_echo_env tests/unit/mcp_plane/test_process_env.py::test_stdio_session_server_env_overrides_admin_extra_env tests/unit/mcp_plane/test_stdio_session.py -q --tb=short
```

Expected: 全部 passed, exit 0。`test_stdio_session_server_env_overrides_admin_extra_env` 若不存在则先补测再跑。

断言要点：`echo_env` + `MCP_TEST_KEY` → `from-advanced-settings`；覆盖场景 → `from-server`。

---

### Task 3: ServerManager invoke 与 provider 热更新

**Files:**
- Test: `tests/unit/mcp_plane/test_server_manager.py`
- Code: `rootseeker/mcp_plane/server_manager.py`

**Interfaces:**
- Consumes: `McpServerManager(extra_env=..., extra_env_provider=...)`
- Consumes: `manager.invoke(server_id, "ext.echo-env.echo_env", {"key": "MCP_TEST_KEY"})`
- Produces: 首次 `first`、变更后 `second`

- [x] **Step 1: 跑 manager 测试**

Run:

```bash
uv run python -m pytest tests/unit/mcp_plane/test_server_manager.py -q --tb=short
```

Expected: 3 passed（含 gateway echo 回归）, exit 0

`test_mcp_extra_env_provider_restarts_session_on_change`：第一次 `first`，改 `env_box` 后第二次 `second`。若第二次仍为 `first`，说明会话未重启。

---

### Task 4: Admin API 写入后注入 runtime

**Files:**
- Test: `tests/unit/apps/test_admin_main.py`
- Code: `apps/admin/main.py`、`apps/admin/config_store.py`

**Interfaces:**
- Consumes: `POST /api/env-vars` body `{key, value, secret, scope}`
- Produces: `app.state.runtime.mcp_server_manager.extra_env`

- [x] **Step 1: 跑 Admin 注入测试**

Run:

```bash
uv run python -m pytest tests/unit/apps/test_admin_main.py::test_upsert_env_var_injects_runtime_scope_into_mcp_manager -q --tb=short
```

Expected: 1 passed, exit 0

`MCP_TEST_TOKEN` 在 extra_env 中；`SKILL_ONLY_TOKEN` 不在。

---

### Task 5: Bootstrap 自动加载 Admin config

**Files:**
- Test: `tests/unit/test_bootstrap_storage.py`（新增用例）
- Code: `rootseeker/bootstrap/runtime.py` `_load_admin_mcp_env` / `create_dev_runtime`

**Interfaces:**
- Consumes: `create_dev_runtime(repo_root)` 且不传 `mcp_extra_env`
- Produces: `runtime.mcp_server_manager.extra_env` 含 Admin runtime 变量

- [x] **Step 1: 确认或补写测试**

```python
def test_create_dev_runtime_loads_admin_advanced_settings_env(
    tmp_path: Path, monkeypatch
) -> None:
    from apps.admin.config_store import AdminConfigStore

    config_path = tmp_path / "admin-config.json"
    store = AdminConfigStore(config_path)
    store.upsert_env_var("BOOTSTRAP_MCP_KEY", "from-advanced", scope="runtime")
    store.upsert_env_var("BOOTSTRAP_SKILL_KEY", "skill-only", scope="skill")
    monkeypatch.setenv("ROOTSEEKER_ADMIN_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")

    runtime = create_dev_runtime(_repo_root())
    try:
        extra = runtime.mcp_server_manager.extra_env
        assert extra["BOOTSTRAP_MCP_KEY"] == "from-advanced"
        assert "BOOTSTRAP_SKILL_KEY" not in extra
    finally:
        runtime.mcp_server_manager._close_all_sessions()
```

- [x] **Step 2: 跑该测试**

Run:

```bash
uv run python -m pytest tests/unit/test_bootstrap_storage.py::test_create_dev_runtime_loads_admin_advanced_settings_env -q --tb=short
```

Expected: 1 passed, exit 0

---

### Task 6: 回归（相关目录全量）

**Files:**
- Test: `tests/unit/mcp_plane/`、`tests/unit/agent_runtime/`、`tests/unit/apps/test_admin_main.py`、`tests/unit/test_bootstrap_storage.py`

- [x] **Step 1: 跑回归套件**

Run:

```bash
uv run python -m pytest tests/unit/mcp_plane/ tests/unit/agent_runtime/ tests/unit/apps/test_admin_main.py tests/unit/test_bootstrap_storage.py -q --tb=line
```

Expected: 0 failed, exit 0

---

## Self-Review

1. **Spec coverage:** T1–T11 覆盖筛选、覆盖、stdio 可见、invoke、热更新、Admin API、bootstrap 自动加载、回归。
2. **Placeholder scan:** 无 TBD；命令与断言齐全。
3. **Type consistency:** `extra_env` / `mcp_runtime_env()` / `echo_env` 与实现一致。

## Execution Results (2026-08-19)

本会话已按 Task 实跑（`uv run python -m pytest ...`，exit 0）：

| Task | 命令范围 | 结果 |
| --- | --- | --- |
| 1 | 3 个 process_env 纯函数用例 | 3 passed |
| 2 | stdio 注入 + 覆盖 + echo 回归 | 4 passed |
| 3 | `test_server_manager.py` | 3 passed |
| 4 | Admin `test_upsert_env_var_injects_runtime_scope_into_mcp_manager` | 1 passed |
| 5 | `test_create_dev_runtime_loads_admin_advanced_settings_env` | 1 passed |
| 6 | `mcp_plane` + `agent_runtime` + `test_admin_main` + `test_bootstrap_storage` | 127 passed, 0 failed |

执行中补测：

- `tests/unit/mcp_plane/test_process_env.py::test_stdio_session_server_env_overrides_admin_extra_env`
- `tests/unit/test_bootstrap_storage.py::test_create_dev_runtime_loads_admin_advanced_settings_env`
