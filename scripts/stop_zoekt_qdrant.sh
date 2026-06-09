#!/usr/bin/env bash
# 停止本机方式启动的 Zoekt / Qdrant（通过 data/run/*.pid）。Docker 启动的请用 docker compose down。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/data/run"

kill_pidfile() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local pid
  pid="$(cat "$f" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "停止 PID $pid ($f)"
    kill "$pid" 2>/dev/null || true
    sleep 0.3
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$f"
}

kill_pidfile "$RUN_DIR/zoekt.pid"
kill_pidfile "$RUN_DIR/qdrant.pid"
echo "完成。"
