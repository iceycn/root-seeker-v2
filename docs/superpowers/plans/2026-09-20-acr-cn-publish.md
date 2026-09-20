# ACR 国内拉取 + GitHub 双推 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Publish 一次构建同时推 Docker Hub 与阿里云 ACR；国内 `setup-cn` 匿名优先拉公开 ACR，失败再回退 Hub 加速。

**Architecture:** 在 `mirrors.py` 集中 ACR 常量与候选 ref；`docker-compose.pull.yml` 用 `APP_IMAGE` / `ZOEKT_IMAGE` / `GITNEXUS_IMAGE` 覆盖仓库名；`publish.yml` 双 login、双打 tag。密码只存在 GitHub Secrets。

**Tech Stack:** GitHub Actions (`docker/login-action`、`docker/build-push-action`)、Docker Compose 环境变量、现有 `scripts/setup` Python 向导、pytest。

## Global Constraints

- ACR 主机：`crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com`
- 命名空间：`root-seeker`
- 三仓库：`root-seeker`、`root-seeker-zoekt`、`root-seeker-gitnexus`
- 禁止把 ACR 密码写入 git、脚本、compose、文档示例
- 国内公开匿名 pull；失败回退现有 DaoCloud / 1ms / Hub
- 继续发布 Docker Hub `wuhun0301/rootseeker-v2{,-zoekt,-gitnexus}`
- 不把 MySQL / Qdrant / Jaeger 推到 ACR；不做 ACK

## File Structure

- Modify: `scripts/setup/mirrors.py` — ACR 常量、候选列表、cn 时写入 compose 镜像变量
- Modify: `tests/unit/setup/test_mirrors.py` — cn/global 候选与 env 赋值
- Modify: `docker-compose.pull.yml` — `APP_IMAGE` / `ZOEKT_IMAGE` / `GITNEXUS_IMAGE`
- Modify: `scripts/setup/docker_path.py` — 本地镜像探测用 `APP_IMAGE`
- Modify: `tests/unit/setup/test_docker_path.py` — cn 路径认 ACR
- Modify: `start.sh` — cn `--pull` 不强制 `DOCKERHUB_USER`
- Modify: `.github/workflows/publish.yml` — ACR login + 双 tag
- Modify: `README.md`、`docker/README.md` — 公开仓与 Secrets 说明

---

### Task 1: ACR 候选 ref 与 cn compose 环境

**Files:**
- Modify: `scripts/setup/mirrors.py`
- Test: `tests/unit/setup/test_mirrors.py`

**Interfaces:**
- Produces: `ACR_REGISTRY: str`, `ACR_NAMESPACE: str`, `acr_repository(name: str) -> str`, `prebuilt_candidates(role: str, *, hub_user: str, tag: str) -> list[str]`, `apply_cn_docker_env` 设置 `APP_IMAGE`/`ZOEKT_IMAGE`/`GITNEXUS_IMAGE` 为不含 tag 的 ACR 仓库名，并把拉到的镜像 tag 成 ACR 名

- [ ] **Step 1: Write the failing tests**

在 `tests/unit/setup/test_mirrors.py` 追加：

```python
from scripts.setup.mirrors import (
    ACR_NAMESPACE,
    ACR_REGISTRY,
    apply_cn_docker_env,
    prebuilt_candidates,
)


def test_prebuilt_candidates_cn_puts_acr_first(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    refs = prebuilt_candidates("app", hub_user="wuhun0301", tag="latest")
    assert refs[0] == f"{ACR_REGISTRY}/{ACR_NAMESPACE}/root-seeker:latest"
    assert any("daocloud" in r and "wuhun0301/rootseeker-v2" in r for r in refs)


def test_prebuilt_candidates_global_has_no_acr(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "global")
    refs = prebuilt_candidates("zoekt", hub_user="wuhun0301", tag="latest")
    assert all(ACR_REGISTRY not in r for r in refs)
    assert refs[0] == "docker.io/wuhun0301/rootseeker-v2-zoekt:latest"


def test_apply_cn_docker_env_sets_acr_compose_images(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    monkeypatch.setattr("scripts.setup.mirrors.ensure_local_image", lambda *_a, **_k: True)
    env = apply_cn_docker_env({"DOCKERHUB_USER": "wuhun0301", "IMAGE_TAG": "latest"})
    assert env["APP_IMAGE"] == f"{ACR_REGISTRY}/{ACR_NAMESPACE}/root-seeker"
    assert env["ZOEKT_IMAGE"].endswith("/root-seeker-zoekt")
    assert env["GITNEXUS_IMAGE"].endswith("/root-seeker-gitnexus")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/setup/test_mirrors.py::test_prebuilt_candidates_cn_puts_acr_first -v`

Expected: FAIL import/attribute `prebuilt_candidates`

- [ ] **Step 3: Write minimal implementation**

在 `scripts/setup/mirrors.py` 增加常量与函数；`apply_cn_docker_env` 在 cn 时写入三变量，并用 `prebuilt_candidates` + `ensure_local_image(f"{repo}:{tag}", candidates)`：

```python
ACR_REGISTRY = "crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com"
ACR_NAMESPACE = "root-seeker"

_ACR_REPOS = {
    "app": "root-seeker",
    "zoekt": "root-seeker-zoekt",
    "gitnexus": "root-seeker-gitnexus",
}
_HUB_REPOS = {
    "app": "rootseeker-v2",
    "zoekt": "rootseeker-v2-zoekt",
    "gitnexus": "rootseeker-v2-gitnexus",
}


def acr_repository(name: str) -> str:
    return f"{ACR_REGISTRY}/{ACR_NAMESPACE}/{name}"


def prebuilt_candidates(role: str, *, hub_user: str, tag: str) -> list[str]:
    hub = f"{hub_user}/{_HUB_REPOS[role]}"
    refs = mirror_hub_refs(hub, tag)
    if is_cn_region():
        return [f"{acr_repository(_ACR_REPOS[role])}:{tag}", *refs]
    return refs
```

`apply_cn_docker_env` 循环 role，设置 `APP_IMAGE` 等，`ensure_local_image` 的 local_name 为 ACR `repo:tag`。Hub 回退成功时 tag 成 ACR 名。MySQL 逻辑保持不变。失败时 `ui.warn` 提示检查 ACR 是否公开。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/setup/test_mirrors.py -v`

Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求提交时）

---

### Task 2: compose 镜像变量 + docker_path 探测 ACR 名

**Files:**
- Modify: `docker-compose.pull.yml`
- Modify: `scripts/setup/docker_path.py`
- Test: `tests/unit/setup/test_docker_path.py`

**Interfaces:**
- Consumes: `APP_IMAGE` / `ZOEKT_IMAGE` / `GITNEXUS_IMAGE`（无 tag）、`IMAGE_TAG`
- Produces: `_run_pull_stack` 用 `APP_IMAGE:IMAGE_TAG` 判断本地是否已有镜像

- [ ] **Step 1: Failing test**

```python
def test_run_pull_stack_cn_inspects_acr_app_image(tmp_path: Path, monkeypatch) -> None:
    from scripts.setup import docker_path

    inspected: list[str] = []

    def fake_present(name: str) -> bool:
        inspected.append(name)
        return True

    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    monkeypatch.setattr(docker_path, "_image_present", fake_present)
    monkeypatch.setattr(docker_path.subprocess, "run", lambda *a, **k: MagicMock(returncode=0))
    env = {
        "APP_IMAGE": "crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com/root-seeker/root-seeker",
        "IMAGE_TAG": "latest",
        "MYSQL_IMAGE": "mysql:8.0",
    }
    code = docker_path._run_pull_stack(tmp_path, env=env, build_only=True)
    assert code == 0
    assert any(n.endswith("/root-seeker/root-seeker:latest") for n in inspected)
```

- [ ] **Step 2: Run test — expect FAIL** because `_run_pull_stack` still inspects `docker.io/{hub}/rootseeker-v2:latest`

- [ ] **Step 3: Implementation**

`docker-compose.pull.yml`：

```yaml
x-app-image: &app-image
  image: ${APP_IMAGE:-docker.io/${DOCKERHUB_USER:-wuhun0301}/rootseeker-v2}:${IMAGE_TAG:-latest}
  pull_policy: missing

services:
  api:
    <<: *app-image
    build: !reset null
  admin:
    <<: *app-image
    build: !reset null
  worker:
    <<: *app-image
    build: !reset null
  scheduler:
    <<: *app-image
    build: !reset null
  zoekt:
    image: ${ZOEKT_IMAGE:-docker.io/${DOCKERHUB_USER:-wuhun0301}/rootseeker-v2-zoekt}:${IMAGE_TAG:-latest}
    pull_policy: missing
    build: !reset null
  gitnexus:
    image: ${GITNEXUS_IMAGE:-docker.io/${DOCKERHUB_USER:-wuhun0301}/rootseeker-v2-gitnexus}:${IMAGE_TAG:-latest}
    pull_policy: missing
    build: !reset null
```

`_run_pull_stack`：

```python
hub_user = env.get("DOCKERHUB_USER", "wuhun0301")
tag = env.get("IMAGE_TAG", "latest")
app_repo = env.get("APP_IMAGE", f"docker.io/{hub_user}/rootseeker-v2")
app_image = f"{app_repo}:{tag}"
```

- [ ] **Step 4: pytest** `tests/unit/setup/test_docker_path.py` PASS

---

### Task 3: `start.sh --pull` 国内不强制 Hub 用户

**Files:**
- Modify: `start.sh`

**Interfaces:**
- Consumes: `ROOTSEEKER_SETUP_REGION`；可选已导出的 `APP_IMAGE` 等
- Produces: cn 时默认导出三 ACR 仓库变量后 `compose pull/up`

- [ ] **Step 1:** 无法对 bash 做同等 pytest；用脚本静态检查：`start.sh` 在 cn 分支不再 `exit 1` 仅因缺少 `DOCKERHUB_USER`。

- [ ] **Step 2: Implementation**（ACR 主机常量，无密码）

```bash
ACR_REGISTRY="${ACR_REGISTRY:-crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com}"
ACR_NAMESPACE="${ACR_NAMESPACE:-root-seeker}"
region="$(printf '%s' "${ROOTSEEKER_SETUP_REGION:-global}" | tr '[:upper:]' '[:lower:]')"
if [ "$USE_PULL" = "1" ]; then
    if [ "$region" = "cn" ] || [ "$region" = "china" ]; then
        export APP_IMAGE="${APP_IMAGE:-${ACR_REGISTRY}/${ACR_NAMESPACE}/root-seeker}"
        export ZOEKT_IMAGE="${ZOEKT_IMAGE:-${ACR_REGISTRY}/${ACR_NAMESPACE}/root-seeker-zoekt}"
        export GITNEXUS_IMAGE="${GITNEXUS_IMAGE:-${ACR_REGISTRY}/${ACR_NAMESPACE}/root-seeker-gitnexus}"
        info "Pulling prebuilt images from ACR (${APP_IMAGE})..."
    else
        if [ -z "${DOCKERHUB_USER:-}" ]; then
            error "使用 --pull 时请设置 DOCKERHUB_USER（Docker Hub 用户名）"
            exit 1
        fi
        export APP_IMAGE="${APP_IMAGE:-docker.io/${DOCKERHUB_USER}/rootseeker-v2}"
        export ZOEKT_IMAGE="${ZOEKT_IMAGE:-docker.io/${DOCKERHUB_USER}/rootseeker-v2-zoekt}"
        export GITNEXUS_IMAGE="${GITNEXUS_IMAGE:-docker.io/${DOCKERHUB_USER}/rootseeker-v2-gitnexus}"
        info "Pulling images from Docker Hub (user=${DOCKERHUB_USER})..."
    fi
    docker compose -f docker-compose.yml -f docker-compose.pull.yml pull
    docker compose -f docker-compose.yml -f docker-compose.pull.yml up -d
fi
```

---

### Task 4: Publish workflow 双推

**Files:**
- Modify: `.github/workflows/publish.yml`

- [ ] **Step 1:** 无密钥的单测不登录 ACR。人工核对 yaml：含 `ACR_REGISTRY`、第二次 `docker/login-action`、每镜像 4 个 tag。

- [ ] **Step 2: Implementation**

`env` 增加 `ACR_REGISTRY`、`ACR_NAMESPACE`。Hub login 之后：

```yaml
      - name: Login to Alibaba Cloud ACR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.ACR_REGISTRY }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}
```

app tags 增加：

```
${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/root-seeker:latest
${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/root-seeker:${{ steps.meta.outputs.VERSION }}
```

zoekt / gitnexus 同理换仓库名。不 `continue-on-error`。

---

### Task 5: 文档

**Files:**
- Modify: `README.md`（国内加速表、`--pull` 说明）
- Modify: `docker/README.md`（ACR 地址表、Secrets 名、公开仓）
- Modify: `docs/superpowers/specs/2026-09-20-acr-cn-publish-design.md` 状态改为已确认

文档示例不得出现密码。说明：控制台三仓公开；GitHub Secrets `ACR_USERNAME` / `ACR_PASSWORD`。

---

## Spec coverage

| Spec | Task |
|------|------|
| Publish 双推 | 4 |
| 国内优先 ACR | 1–3 |
| 公开匿名、无密码入库 | 1、4、5 |
| compose 变量 + DOCKERHUB_USER 默认 | 2–3 |
| ACR 失败回退 Hub | 1 `ensure_local_image` 候选链 |
| 单测 cn 候选 ACR 在前 | 1 |
| 运维 Secrets / 公开仓 | 5 文档 + 人工 |

## Placeholder scan

无 TBD。Commit 步骤仅在用户明确要求时执行。
