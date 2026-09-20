# Docker 部署包

本目录与仓库根目录的 Compose / Dockerfile 一起，构成 RootSeeker V2 的公开 Docker 部署包。

## 包含内容

| 路径 | 说明 |
| --- | --- |
| [`../Dockerfile`](../Dockerfile) | API / Admin / Worker / Scheduler 多阶段构建 |
| [`../docker-compose.yml`](../docker-compose.yml) | 完整栈：api、admin、worker、scheduler、zoekt、qdrant、gitnexus |
| [`../docker-compose.hybrid.yml`](../docker-compose.hybrid.yml) | Hybrid：仅索引侧车，本机跑 Python |
| [`../.env.docker`](../.env.docker) | 环境变量模板（复制为 `.env`） |
| [`../.dockerignore`](../.dockerignore) | 构建上下文排除 `data/`、`repos/` 等，避免镜像虚胖 |
| `Dockerfile.zoekt` | Zoekt 搜索 + `:6071` 远程索引 HTTP |
| `Dockerfile.gitnexus` | GitNexus 知识图谱 sidecar |
| `bin/zoekt-*` | 预置 Linux amd64 二进制（也可重新下载） |
| `prepare-zoekt.ps1` / `prepare-zoekt.sh` | 从 GitHub Release 下载 Zoekt 二进制 |

## 一键启动（仓库根目录）

```bash
cp .env.docker .env
./start.sh
# 或
docker compose up -d --build
```

Windows：

```bat
start.bat
```

## 构建 Zoekt 前准备二进制

若 `docker/bin/zoekt-index` / `zoekt-webserver` 缺失：

```bash
bash docker/prepare-zoekt.sh
# Windows:
# powershell -File docker/prepare-zoekt.ps1
```

## 服务地址

| 服务 | 地址 |
| --- | --- |
| API | http://localhost:8000 |
| Admin | http://localhost:8010 |
| Zoekt 搜索 / 索引 | http://localhost:6070 · http://localhost:6071 |
| Qdrant | http://localhost:6333 |
| GitNexus | http://localhost:7474 |

公开源码仓库：https://github.com/iceycn/root-seeker-v2

## 推送到 Docker Hub / 阿里云 ACR

```powershell
docker login
.\scripts\push-dockerhub.ps1
# 默认推送到 wuhun0301；可覆盖: -User othername
```

GitHub Actions `Publish` 在构建时同时推送：

- Docker Hub（`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`）
- 阿里云 ACR 杭州个人版（`ACR_USERNAME` / `ACR_PASSWORD`）

ACR 主机：`crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com`  
命名空间：`root-seeker`。三个仓库须在控制台设为**公开**，国内一键脚本才能匿名拉取。

已发布镜像（`wuhun0301` / ACR `root-seeker`）：

- Hub: [wuhun0301/rootseeker-v2](https://hub.docker.com/r/wuhun0301/rootseeker-v2)（api / admin / worker / scheduler 共用）
- Hub: [wuhun0301/rootseeker-v2-zoekt](https://hub.docker.com/r/wuhun0301/rootseeker-v2-zoekt)
- Hub: [wuhun0301/rootseeker-v2-gitnexus](https://hub.docker.com/r/wuhun0301/rootseeker-v2-gitnexus)
- ACR: `crpi-b41zzjy8qjnhgc6o.cn-hangzhou.personal.cr.aliyuncs.com/root-seeker/root-seeker`
- ACR: `…/root-seeker/root-seeker-zoekt`
- ACR: `…/root-seeker/root-seeker-gitnexus`

## 从预构建镜像拉取启动

```bash
# 国际 Docker Hub
export DOCKERHUB_USER=wuhun0301
./start.sh --pull
# 或
docker compose -f docker-compose.yml -f docker-compose.pull.yml up -d

# 国内 ACR（仓库须公开，无需 docker login）
ROOTSEEKER_SETUP_REGION=cn ./start.sh --pull
```
