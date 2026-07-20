# 交互式安装向导 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现跨平台（Windows/macOS/Linux）渐进式交互安装向导：有 Docker 优先 Compose 全栈；无 Docker 走本机完整安装（存储三选一 + 尽量装索引器）。

**Architecture:** 薄包装 `setup.ps1`/`setup.sh` 调用 `scripts/setup_wizard.py`；业务拆到 `scripts/setup/*` 模块；进度存 `.setup-state.json`；仅 `env_writer` 写 `.env`。

**Tech Stack:** Python 3.11+（标准库为主：argparse、urllib、subprocess、venv、json、pathlib）；复用现有 `docker compose`、`scripts/init_mysql.py`、`docker/prepare-zoekt.*`、`scripts/sync-compose-storage.sh`。

**Spec:** `docs/superpowers/specs/2026-07-20-interactive-setup-wizard-design.md`

## Global Constraints

- 支持 OS：Windows、macOS、Linux
- Python 最低：3.11（低于则失败退出）
- Docker 可用（CLI + daemon）→ 默认路径 docker；否则默认 native
- 本机 MySQL「安装」= 便携包到 `.tools/`，默认端口 3307
- 索引失败可跳过，不得阻断 API/Admin
- `.tools/`、`.setup-state.json` 必须 gitignore
- 用户可见文案与流程提示：**中文**
- 不替换 `start.sh`/`start.bat` 的日常用途
- TDD：每个任务先写失败测试再实现（可 mock 网络/进程）

---

## File map（将创建/修改）

| 路径 | 职责 |
|------|------|
| `setup.sh` | macOS/Linux 入口 |
| `setup.ps1` | Windows 入口 |
| `scripts/setup_wizard.py` | CLI + 交互编排 |
| `scripts/setup/__init__.py` | 包标记 |
| `scripts/setup/ui.py` | 中文提示、确认、单选 |
| `scripts/setup/state.py` | 进度读写 |
| `scripts/setup/detect.py` | 环境探测 |
| `scripts/setup/env_writer.py` | `.env` 原子合并 |
| `scripts/setup/health.py` | `/healthz` 轮询 |
| `scripts/setup/docker_path.py` | Docker 路径步骤 |
| `scripts/setup/native_path.py` | venv/pip/uvicorn |
| `scripts/setup/portable_mysql.py` | 便携 MySQL |
| `scripts/setup/existing_mysql.py` | 已有 MySQL |
| `scripts/setup/indexers.py` | Zoekt/Qdrant/GitNexus |
| `tests/unit/setup/test_*.py` | 单测 |
| `.gitignore` | 忽略 `.tools/`、`.setup-state.json` |
| `README.md` | 增加「首次安装」入口说明 |

---

### Task 1: 进度 state + `.env` 合并 + gitignore

**Files:**
- Create: `scripts/setup/__init__.py`
- Create: `scripts/setup/state.py`
- Create: `scripts/setup/env_writer.py`
- Create: `tests/unit/setup/test_state.py`
- Create: `tests/unit/setup/test_env_writer.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces:
  - `SetupState.load(path: Path) -> SetupState`
  - `SetupState.save(path: Path) -> None`
  - `SetupState.mark_done(step: str, meta: dict | None = None) -> None`
  - `SetupState.is_done(step: str) -> bool`
  - `merge_env_file(path: Path, updates: dict[str, str], *, overwrite_existing: bool = False) -> None`

- [x] **Step 1: 写失败测试 — state 续跑**

```python
# tests/unit/setup/test_state.py
from pathlib import Path
from scripts.setup.state import SetupState

def test_mark_done_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / ".setup-state.json"
    s = SetupState()
    s.mark_done("detect", {"os": "windows"})
    s.save(path)
    loaded = SetupState.load(path)
    assert loaded.is_done("detect")
    assert loaded.meta("detect")["os"] == "windows"
```

- [x] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/setup/test_state.py -v`  
Expected: FAIL（模块不存在）

- [x] **Step 3: 实现 `state.py`**

`SetupState` 内部结构：`{"version": 1, "steps": {"detect": {"done": true, "meta": {...}}}}`  
`load` 文件不存在则返回空状态；`save` 原子写。

- [x] **Step 4: 写失败测试 — env 合并不覆盖密钥**

```python
# tests/unit/setup/test_env_writer.py
from pathlib import Path
from scripts.setup.env_writer import merge_env_file

def test_merge_preserves_existing_secret(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("ROOTSEEKER_LLM_API_KEY=keep-me\nFOO=1\n", encoding="utf-8")
    merge_env_file(path, {"FOO": "2", "ROOTSEEKER_LLM_API_KEY": "new"}, overwrite_existing=False)
    text = path.read_text(encoding="utf-8")
    assert "ROOTSEEKER_LLM_API_KEY=keep-me" in text
    assert "FOO=2" in text
```

- [x] **Step 5: 实现 `env_writer.py` + 跑通上述测试**

解析 `.env` 行（忽略注释/空行）；合并键；`overwrite_existing=False` 时已存在键保留；用临时文件 + replace。

- [x] **Step 6: `.gitignore` 增加**

```gitignore
.tools/
.setup-state.json
```

- [x] **Step 7: 提交（若用户要求再 commit；否则跳过）**

---

### Task 2: 环境探测 + UI 基础

**Files:**
- Create: `scripts/setup/detect.py`
- Create: `scripts/setup/ui.py`
- Create: `tests/unit/setup/test_detect.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `@dataclass EnvInfo: os_name, python_version, python_ok, docker_cli, docker_daemon, ports_in_use: dict[int,bool]`
  - `detect_environment(repo_root: Path) -> EnvInfo`
  - `ui.confirm(prompt: str, default: bool = True) -> bool`
  - `ui.choose(prompt: str, options: list[tuple[str,str]], default: str) -> str`  # (id, 中文标签)
  - `ui.info/ok/warn/error(msg: str) -> None`

- [x] **Step 1: 写失败测试 — Docker daemon 探测**

```python
def test_detect_docker_daemon_false_when_cli_missing(monkeypatch) -> None:
    monkeypatch.setattr("scripts.setup.detect.shutil.which", lambda _: None)
    info = detect_environment(Path("."))
    assert info.docker_cli is False
    assert info.docker_daemon is False
```

- [x] **Step 2: 实现 `detect.py`**

- `python_ok = sys.version_info >= (3, 11)`
- `docker_cli = shutil.which("docker") is not None`
- `docker_daemon`: 运行 `docker info`（超时 5s），returncode==0 则 True
- `ports_in_use`: 对 8000/8010/3306/3307/6070/6333 做 socket connect 探测

- [x] **Step 3: 实现 `ui.py`（中文）**

非 TTY 或 `ROOTSEEKER_SETUP_NONINTERACTIVE=1` 时：`confirm` 返回 default；`choose` 返回 default。

- [x] **Step 4: 跑通 `tests/unit/setup/test_detect.py`**

---

### Task 3: 健康检查 + CLI 骨架

**Files:**
- Create: `scripts/setup/health.py`
- Create: `scripts/setup_wizard.py`
- Create: `tests/unit/setup/test_cli_args.py`
- Create: `tests/unit/setup/test_health.py`

**Interfaces:**
- Produces:
  - `wait_http_ok(url: str, timeout_seconds: float = 120.0, interval: float = 2.0) -> bool`
  - `parse_args(argv: list[str] | None) -> argparse.Namespace` with fields: `yes`, `path` (`docker|native|None`), `storage` (`mysql|sqlite|existing-mysql|None`), `resume`, `status`, `build_only`
  - `main(argv) -> int`

- [x] **Step 1: 测试 CLI 解析**

```python
def test_parse_yes_requires_path_in_main(monkeypatch) -> None:
    # --yes 无 --path 时 main 返回非 0
    code = main(["--yes", "--storage", "sqlite"])
    assert code != 0
```

- [x] **Step 2: 实现 `health.py`（urllib 轮询）与 `setup_wizard.py` 参数解析骨架**

`main` 暂只实现：`--status` 打印 state；`--yes` 缺参退出；交互入口先打印「尚未实现路径」返回 2（后续任务补齐）。

- [x] **Step 3: 测试通过**

---

### Task 4: Docker 路径

**Files:**
- Create: `scripts/setup/docker_path.py`
- Create: `tests/unit/setup/test_docker_path.py`
- Modify: `scripts/setup_wizard.py`

**Interfaces:**
- Consumes: `merge_env_file`, `SetupState`, `ui`, `wait_http_ok`, `detect_environment`
- Produces: `run_docker_path(repo_root: Path, *, build_only: bool, storage: str, state: SetupState, noninteractive: bool) -> int`

- [x] **Step 1: 测试 — 写入默认 mysql env 键**

Mock subprocess；断言 `merge_env_file` 被调用且包含：

```python
{
  "ROOTSEEKER_STORAGE_BACKEND": "mysql",
  "COMPOSE_PROFILES": "mysql",
  "ROOTSEEKER_MYSQL_HOST": "mysql",
}
```

storage=`sqlite` 时：

```python
{"ROOTSEEKER_STORAGE_BACKEND": "sqlite", "COMPOSE_PROFILES": ""}
```

- [x] **Step 2: 实现 `docker_path.py`**

顺序：
1. 若无 `.env`：从 `.env.docker` 复制再 merge（或直接 merge 模板键）
2. 按 storage 写 backend / COMPOSE_PROFILES
3. 交互可选 LLM（非交互跳过）
4. `ensure_zoekt`：若缺 `docker/bin/zoekt-index`，调用现有 `docker/prepare-zoekt.sh` 或 `.ps1`（按 OS）
5. `subprocess.run(["docker", "compose", "build"], check=False)`；若非 build_only 再 `up -d --build`
6. `wait_http_ok` API/Admin
7. `state.mark_done("docker_up")`

- [x] **Step 3: 向导接入路径 A；跑单测**

---

### Task 5: 本机路径 — venv/pip + SQLite 存储

**Files:**
- Create: `scripts/setup/native_path.py`
- Create: `tests/unit/setup/test_native_path.py`
- Modify: `scripts/setup_wizard.py`

**Interfaces:**
- Produces:
  - `ensure_venv(repo_root: Path) -> Path`  # 返回 python 可执行文件路径
  - `pip_install_project(python: Path, repo_root: Path) -> int`
  - `configure_sqlite(repo_root: Path) -> None`
  - `start_uvicorn(python: Path, repo_root: Path, *, module: str, port: int, pid_key: str, state: SetupState) -> None`
  - `run_native_path(..., storage: str, ...) -> int`（本任务先支持 sqlite 端到端到「配置完成」；启动可 mock）

- [x] **Step 1: 测试 configure_sqlite 写 env**

- [x] **Step 2: 实现 venv 创建（`python -m venv .venv`）、pip install、sqlite 配置**

- [x] **Step 3: 实现后台启动 uvicorn（Unix: subprocess + start_new_session；Windows: CREATE_NEW_PROCESS_GROUP / DETACHED）；PID 写入 state.meta**

- [x] **Step 4: 向导：storage=sqlite 时可跑通本机路径（索引器下一步再接）**

---

### Task 6: 已有 MySQL + 便携 MySQL（核心）

**Files:**
- Create: `scripts/setup/existing_mysql.py`
- Create: `scripts/setup/portable_mysql.py`
- Create: `tests/unit/setup/test_portable_mysql.py`
- Create: `tests/unit/setup/test_existing_mysql.py`
- Modify: `scripts/setup/native_path.py`

**Interfaces:**
- Produces:
  - `probe_mysql(host, port, user, password, database) -> tuple[bool, str]`
  - `configure_existing_mysql(repo_root, *, host, port, user, password, database) -> int`  # 写 env + 调 init_mysql.py
  - `MYSQL_VERSION = "8.0.40"`（或实现时选定的钉死版本）
  - `resolve_mysql_download(os_name: str, arch: str) -> tuple[str, str | None]`  # url, sha256_or_none
  - `ensure_portable_mysql(repo_root: Path, *, port: int = 3307) -> tuple[bool, str]`
  - `stop_portable_mysql(repo_root: Path) -> None`

- [x] **Step 1: 测试 resolve_mysql_download 三端 URL 非空且互不相同**

```python
def test_resolve_urls_differ_by_platform() -> None:
    win, _ = resolve_mysql_download("windows", "amd64")
    lin, _ = resolve_mysql_download("linux", "amd64")
    mac, _ = resolve_mysql_download("darwin", "arm64")
    assert "win" in win.lower() or "windows" in win.lower()
    assert win != lin != mac
```

- [x] **Step 2: 实现下载（urllib）、解压、`--initialize-insecure`、后台 mysqld、写 `.tools/mysql.pid`、merge env（host=127.0.0.1 port=3307）、`python scripts/init_mysql.py`**

下载缓存：若归档已存在且 checksum 匹配则跳过下载（满足「续跑不重复下载」）。

- [x] **Step 3: existing_mysql：PyMySQL 或 subprocess `mysqladmin ping` 探测；失败返回中文原因**

- [x] **Step 4: native_path 接入三种 storage；交互用 `ui.choose` 中文三项**

- [x] **Step 5: 单测 mock 下载/解压/进程**

---

### Task 7: 本机索引器（尽力 + 可跳过）

**Files:**
- Create: `scripts/setup/indexers.py`
- Create: `tests/unit/setup/test_indexers.py`
- Modify: `scripts/setup/native_path.py`

**Interfaces:**
- Produces: `setup_indexers(repo_root, state, *, noninteractive: bool) -> dict[str, str]`  
  返回 `{"zoekt": "ok|skipped:原因", "qdrant": "...", "gitnexus": "..."}`

- [x] **Step 1: 测试 — Zoekt 已存在二进制时标记 ok 且不下载**

- [x] **Step 2: 实现**
  - Zoekt：复用 prepare 脚本；启动命令写入文档化常量；失败 → skipped
  - Qdrant：下载 release 到 `.tools/qdrant/`（URL 钉死）；失败 skipped
  - GitNexus：`shutil.which("node")` 等探测；不能起则 skipped，提示用 Docker

- [x] **Step 3: native_path 在存储配置后调用；汇总中文打印**

---

### Task 8: 包装脚本 + 向导主流程串起来 + README

**Files:**
- Create: `setup.sh`
- Create: `setup.ps1`
- Modify: `scripts/setup_wizard.py`（完整交互流程）
- Modify: `README.md`（首次安装一节，中文）
- Modify: `docs/superpowers/specs/2026-07-20-interactive-setup-wizard-design.md` 状态改为「已确认」

**Interfaces:**
- 包装器：定位仓库根 → 找 `python`/`python3` → `exec`/`&` 调用 `scripts/setup_wizard.py @args`

- [x] **Step 1: 实现完整 `main` 流程（对照 spec 中文流程图）**

顺序固定：
1. 欢迎（中文）
2. detect → 展示结果
3. 选择 path（默认随 Docker）
4. 分支 docker / native
5. 结束摘要 + 常用命令

处理 `--resume`：跳过 `state.is_done` 步骤。  
Ctrl+C：save state，打印 `python scripts/setup_wizard.py --resume`。

- [x] **Step 2: `setup.sh` / `setup.ps1`**

```bash
#!/usr/bin/env bash
# setup.sh 核心：cd 到仓库根，exec python3 scripts/setup_wizard.py "$@"
```

```powershell
# setup.ps1 核心：Set-Location 仓库根；python scripts/setup_wizard.py @args
```

- [x] **Step 3: README 增加「首次安装」**

```markdown
## 首次安装（推荐）

Windows: `.\setup.ps1`
macOS / Linux: `./setup.sh`

向导会自动探测 Docker；无 Docker 则引导本机安装。
```

- [x] **Step 4: 跑全量 setup 单测**

Run: `python -m pytest tests/unit/setup/ -q`  
Expected: 全部 PASS

---

## Spec 覆盖自检

| Spec 要求 | 任务 |
|-----------|------|
| Docker 优先自动探测 | Task 2 + 8 |
| 本机完整安装 | Task 5–7 |
| Win/macOS/Linux 包装 | Task 8 |
| 存储三选一 | Task 5–6 |
| 便携 MySQL `.tools/` 端口 3307 | Task 6 |
| 索引尽力可跳过 | Task 7 |
| 续跑 state | Task 1 + 8 |
| 非交互 CLI | Task 3 + 8 |
| 不替换 start.sh | Task 8（仅文档说明） |
| gitignore | Task 1 |
| 健康检查 | Task 3–5 |
| 中文 UI | Task 2 + 8 |

## 执行方式（完成后由你选）

计划已保存到 `docs/superpowers/plans/2026-07-20-interactive-setup-wizard.md`。

**1. Subagent-Driven（推荐）** — 每任务新开子代理，任务间审查  
**2. Inline Execution** — 本会话按任务连续实现并设检查点  

你要哪一种？
