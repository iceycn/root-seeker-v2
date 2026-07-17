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

公开仓库：https://github.com/iceycn/root-seeker-v2
