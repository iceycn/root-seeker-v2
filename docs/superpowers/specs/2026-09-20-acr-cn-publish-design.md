# 国内一键启动走阿里云 ACR + GitHub 双推 — 设计说明

日期：2026-09-20  
状态：已确认  
相关文档：`.github/workflows/publish.yml`、`docker-compose.pull.yml`、`scripts/setup/mirrors.py`、`scripts/setup/docker_path.py`、`setup-cn.sh`、`setup-cn.ps1`

## 目标

1. GitHub `Publish` 在构建 Docker 镜像时，**同时推送到 Docker Hub 与阿里云容器镜像服务 ACR**。
2. 国内一键入口（`setup-cn.sh` / `setup-cn.ps1`，以及 `ROOTSEEKER_SETUP_REGION=cn`）**优先从公开 ACR 拉取**预构建镜像，不再依赖 Docker Hub 代理作为第一选择。
3. ACR 仓库设为**公开拉取**，终端用户无需 `docker login`，脚本与仓库中**不得出现** ACR 密码。

不做：

- 阿里云 ACK / Kubernetes 部署（仍用现有 `k8s/` 与 `start.sh k8s`）
- 把 MySQL / Qdrant / Jaeger 推到 ACR
- 去掉 Docker Hub 发布（海外与现有用户继续用 Hub）

## 已锁定决策

| 议题 | 选择 |
|------|------|
| 云产品 | ACR 个人版镜像仓库，不是 ACK |
| 推送方式 | 同一套 `publish.yml` 一次构建、双 registry 打 tag（方案 A） |
| 仓库拆分 | 命名空间 `root-seeker` 下三个仓库，与 Hub 三镜像对应 |
| 国内拉取 | 公开仓匿名 `docker pull`；失败再回退现有 DaoCloud / Hub |
| 密钥 | GitHub Secrets `ACR_USERNAME` / `ACR_PASSWORD`；registry 主机名可写死在 workflow |

## 镜像映射

Registry 公网主机：`crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com`  
命名空间：`root-seeker`

| 角色 | Docker Hub | ACR |
|------|------------|-----|
| api / admin / worker / scheduler | `wuhun0301/rootseeker-v2` | `…/root-seeker/root-seeker` |
| zoekt | `wuhun0301/rootseeker-v2-zoekt` | `…/root-seeker/root-seeker-zoekt` |
| gitnexus | `wuhun0301/rootseeker-v2-gitnexus` | `…/root-seeker/root-seeker-gitnexus` |

Tag 两边一致：`latest`，以及 `sha-<7位>`（branch push）或 release 的 git tag 名。

个人版首次 `docker push` 通常会自动创建 `root-seeker-zoekt`、`root-seeker-gitnexus`。发布前须在控制台将三个仓库均设为**公开**。

## 发布流水线

`.github/workflows/publish.yml`：

1. 现有 `docker/login-action` 登录 Docker Hub（`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`）。
2. 新增第二次 login：`registry` 为上述 ACR 主机，`username` / `password` 来自 `ACR_USERNAME` / `ACR_PASSWORD`。
3. 每个 `docker/build-push-action` 的 `tags` 同时列出 Hub 与 ACR 两组（`latest` + 版本 tag）。
4. ACR login 或 push 失败则整个 job 失败，避免国内脚本拉到空仓。
5. Fork PR 不跑本 workflow 的 push（保持现有 `on.push` / `release` / `workflow_dispatch`）；无 ACR secret 的仓库无法成功发布，属预期。

常量（非 secret）可放在 `env`：

- `ACR_REGISTRY=crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com`
- `ACR_NAMESPACE=root-seeker`

## 国内 Compose 拉取

不复制整份 compose。扩展 `docker-compose.pull.yml`，用环境变量覆盖镜像，默认仍指向 Hub（保留 `DOCKERHUB_USER` 作为默认拼接）：

- `APP_IMAGE` 默认 `docker.io/${DOCKERHUB_USER:-wuhun0301}/rootseeker-v2`
- `ZOEKT_IMAGE` 默认 `docker.io/${DOCKERHUB_USER:-wuhun0301}/rootseeker-v2-zoekt`
- `GITNEXUS_IMAGE` 默认 `docker.io/${DOCKERHUB_USER:-wuhun0301}/rootseeker-v2-gitnexus`
- `IMAGE_TAG` 默认 `latest`（已有）

完整 ref：`${APP_IMAGE}:${IMAGE_TAG}`。变量值为**不含 tag 的仓库名**。

`start.sh --pull`：`global` 仍可要求 `DOCKERHUB_USER`；`cn` 不强制 Hub 用户名，改用 ACR 默认仓库。

`scripts/setup/mirrors.py` 在 `cn` 区域：

1. 将上述三个变量设为 ACR 完整仓库名（不含 tag）。
2. `ensure_local_image` 的候选列表：**ACR 在前**，其后保持现有 DaoCloud / `docker.1ms.run` / Hub。
3. MySQL 逻辑不变（清华/DaoCloud `library/mysql`）。

`docker_path.py` / `start.sh --pull`：国内路径下检测本地镜像时认 ACR 名，而不是只认 `docker.io/wuhun0301/...`。

`setup-cn.sh` / `setup-cn.ps1` 仍只设 `ROOTSEEKER_SETUP_REGION=cn`，不写账号密码。

## 错误处理

- CI：ACR 认证失败、某个镜像 push 失败 → job 失败。
- 本机国内 pull：ACR 超时或 404 → 警告后按现有 Hub 加速链继续；三件套都失败才让向导失败。
- 用户未把仓设为公开时：pull 会 401/403，同样走 Hub 回退，并提示检查 ACR 公开设置。

## 安全

- 禁止把 ACR 密码写入 git、脚本、compose、文档示例。
- 聊天中出现过的口令应在阿里云控制台轮换，再写入 GitHub Secrets。
- 文档只写：控制台设公开仓；仓库 Settings → Secrets 配置 `ACR_USERNAME`、`ACR_PASSWORD`。

## 文档

- `README.md` 国内加速说明：预构建镜像来自杭州 ACR，需公开仓。
- `docker/README.md` 增加 ACR 地址表与双推说明。
- 不把 registry 密码写进 release notes 正文以外的任何文件。

## 测试

- `tests/unit/setup/test_mirrors.py`：`cn` 时 app/zoekt/gitnexus 候选首项为 ACR；`global` 不含 ACR。
- compose 默认值仍为 Hub，避免非国内用户行为变化。
- 不在 GitHub Actions 单测里真实登录 ACR。

## 运维清单（人工，不写进代码）

1. ACR 控制台创建或确认三个仓库，均设公开。
2. GitHub 仓库配置 `ACR_USERNAME`、`ACR_PASSWORD`。
3. 在 `main` 上 `workflow_dispatch` 一次 Publish，确认 Hub 与 ACR 均有 `latest`。
4. 国内机器无登录执行 `docker pull <acr>/root-seeker/root-seeker:latest` 验证匿名拉取。
