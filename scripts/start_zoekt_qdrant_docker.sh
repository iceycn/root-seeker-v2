#!/usr/bin/env bash
# 可选：用 Docker Compose 拉起 Zoekt(6070) + Qdrant(6333)。无 Docker 请用 ./scripts/start_zoekt_qdrant.sh（本机二进制）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v docker >/dev/null 2>&1; then
  DOCKER=docker
elif [[ -x "/Applications/Docker.app/Contents/Resources/bin/docker" ]]; then
  DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
else
  echo "错误: 未找到 docker。无 Docker 时使用: ./scripts/start_zoekt_qdrant.sh" >&2
  exit 1
fi

compose() {
  if $DOCKER compose version >/dev/null 2>&1; then
    $DOCKER compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "错误: 需要 Docker Compose（docker compose 或 docker-compose）。" >&2
    exit 1
  fi
}

mkdir -p "$ROOT/data/repos"
echo "Docker: 构建并启动 zoekt 与 qdrant …"
compose --profile codesearch up -d --build zoekt qdrant
echo "完成。探测: python3 scripts/smoke_zoekt_qdrant.py"
