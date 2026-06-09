#!/usr/bin/env bash
# 一键真实联调（无 Docker）：本机 Zoekt + Qdrant → 示例仓 zoekt-index → API repo sync → 语义搜索。
# 依赖：./scripts/start_zoekt_qdrant.sh 能成功（本机 qdrant + zoekt-webserver）。
# 若使用 Docker 起索引服务，请使用 scripts/start_zoekt_qdrant_docker.sh 后自行确保宿主机可执行 zoekt-index。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

bash "$ROOT/scripts/start_zoekt_qdrant.sh"

echo "等待 Zoekt :6070 / Qdrant :6333 …"
python3 <<'WAITPY'
import socket
import time

def wait_port(host: str, port: int, seconds: float = 90.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            if s.connect_ex((host, port)) == 0:
                return True
        finally:
            s.close()
        time.sleep(0.5)
    return False

if not wait_port("127.0.0.1", 6333):
    raise SystemExit("Qdrant 未就绪，请看 data/run/qdrant.log")
if not wait_port("127.0.0.1", 6070):
    raise SystemExit("Zoekt 未就绪，请看 data/run/zoekt.log")
print("端口就绪")
WAITPY

if [[ -z "${ROOTSEEKER_ZOEKT_INDEX_BINARY:-}" ]]; then
  if command -v zoekt-index >/dev/null 2>&1; then
    ROOTSEEKER_ZOEKT_INDEX_BINARY="$(command -v zoekt-index)"
  elif command -v go >/dev/null 2>&1 && [[ -x "$(go env GOPATH)/bin/zoekt-index" ]]; then
    ROOTSEEKER_ZOEKT_INDEX_BINARY="$(go env GOPATH)/bin/zoekt-index"
  else
    echo "错误: 未找到 zoekt-index。执行: go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest" >&2
    exit 1
  fi
fi
export ROOTSEEKER_ZOEKT_INDEX_BINARY

mkdir -p "$ROOT/data/repos"
SMOKE="$ROOT/data/repos/smoke_mini"
if [[ ! -d "$SMOKE/.git" ]]; then
  echo "创建本地示例 git 仓库到 data/repos/smoke_mini …"
  mkdir -p "$SMOKE/src"
  cat >"$SMOKE/README.md" <<'EOF'
# smoke mini

This repository is used to verify RootSeeker code search indexing.
EOF
  cat >"$SMOKE/src/app.py" <<'EOF'
def readme_smoke_handler():
    return "readme smoke handler"
EOF
  git -C "$SMOKE" init >/dev/null
  git -C "$SMOKE" add README.md src/app.py
  git -C "$SMOKE" -c user.name=RootSeeker -c user.email=rootseeker@example.local commit -m "init smoke repo" >/dev/null
fi

IDX="$ROOT/data/zoekt/index"
echo "本机 zoekt-index: -index $IDX $SMOKE"
"$ROOTSEEKER_ZOEKT_INDEX_BINARY" -index "$IDX" "$SMOKE"
sleep 2

export ZOEKT_ENDPOINT="${ZOEKT_ENDPOINT:-http://127.0.0.1:6070}"
export QDRANT_ENDPOINT="${QDRANT_ENDPOINT:-http://127.0.0.1:6333}"
export ROOTSEEKER_ZOEKT_ENDPOINT="${ROOTSEEKER_ZOEKT_ENDPOINT:-$ZOEKT_ENDPOINT}"
export ROOTSEEKER_QDRANT_ENDPOINT="${ROOTSEEKER_QDRANT_ENDPOINT:-$QDRANT_ENDPOINT}"
export ROOTSEEKER_ZOEKT_INDEX_DIR="${ROOTSEEKER_ZOEKT_INDEX_DIR:-$IDX}"
export ROOTSEEKER_REPO_BASE_PATH="${ROOTSEEKER_REPO_BASE_PATH:-$ROOT/data/api-repos}"
export API_PORT="${API_PORT:-8899}"

"$PYTHON" "$ROOT/scripts/smoke_zoekt_qdrant.py"
"$PYTHON" "$ROOT/scripts/real_codesearch_integration.py" --expect-zoekt-hits

API_BASE="http://127.0.0.1:${API_PORT}"
API_LOG="$ROOT/data/run/api-smoke.log"
API_PID_FILE="$ROOT/data/run/api-smoke.pid"

echo "启动 API 做真实 repo/index/semantic-search 验收: $API_BASE"
"$PYTHON" -m uvicorn apps.api.main:app --host 127.0.0.1 --port "$API_PORT" >>"$API_LOG" 2>&1 &
API_PID=$!
echo "$API_PID" >"$API_PID_FILE"

cleanup_api() {
  if kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
  rm -f "$API_PID_FILE"
}
trap cleanup_api EXIT

"$PYTHON" <<'WAITAPI'
import os
import time
import httpx

base = f"http://127.0.0.1:{os.environ.get('API_PORT', '8899')}"
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        r = httpx.get(f"{base}/healthz", timeout=2.0, trust_env=False)
        if r.status_code == 200:
            print("API 就绪")
            raise SystemExit(0)
    except Exception:
        pass
    time.sleep(0.5)
raise SystemExit("API 未就绪，请看 data/run/api-smoke.log")
WAITAPI

echo "API: 注册 smoke repo"
curl -sS -X POST "$API_BASE/repos" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"smoke-mini\",\"url\":\"$SMOKE\",\"branch\":\"master\"}" | "$PYTHON" -m json.tool

echo "API: 同步并触发 Zoekt/Qdrant 索引"
curl -sS -X POST "$API_BASE/repos/smoke-mini/sync" \
  -H 'Content-Type: application/json' \
  -d '{"trigger_index":true}' | tee "$ROOT/data/run/api-sync-response.json" | "$PYTHON" -m json.tool

echo "API: 索引状态"
curl -sS "$API_BASE/repos/smoke-mini/index-status" | "$PYTHON" -m json.tool

echo "API: 语义搜索"
SEARCH_JSON="$(curl -sS -X POST "$API_BASE/code/semantic-search" \
  -H 'Content-Type: application/json' \
  -d '{"query":"readme smoke handler","repo_name":"smoke-mini","limit":5}')"
echo "$SEARCH_JSON" | "$PYTHON" -m json.tool
"$PYTHON" - "$SEARCH_JSON" <<'ASSERTPY'
import json
import sys

data = json.loads(sys.argv[1])
items = data.get("result") or []
if not data.get("ok"):
    raise SystemExit(f"semantic search failed: {data}")
if not items:
    raise SystemExit("semantic search returned no Qdrant hits")
print(f"语义搜索命中: {len(items)}")
ASSERTPY

echo "真实联调完成。"
