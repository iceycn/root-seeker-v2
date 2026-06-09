#!/usr/bin/env bash
# 本机启动 Zoekt(:6070) + Qdrant(:6333)，不依赖 Docker。
# 前置：
#   • Zoekt：需 Go 1.21+，执行:
#       go install github.com/sourcegraph/zoekt/cmd/zoekt-webserver@latest
#       go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest
#     并将 $(go env GOPATH)/bin 加入 PATH（常见为 ~/go/bin）。
#   • Qdrant：从 https://github.com/qdrant/qdrant/releases 下载对应平台二进制到 PATH，
#     或设置 ROOTSEEKER_QDRANT_BINARY=/绝对路径/qdrant
# 配置：Qdrant 使用仓库内 config/qdrant_config.yaml（cwd 为项目根）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/data/run"
mkdir -p "$RUN_DIR" "$ROOT/data/zoekt/index" "$ROOT/data/qdrant_storage" "$ROOT/data/repos"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

go_bin() {
  if command -v go >/dev/null 2>&1; then
    echo "$(go env GOPATH)/bin"
  fi
}

resolve_qdrant() {
  if [[ -n "${ROOTSEEKER_QDRANT_BINARY:-}" && -x "${ROOTSEEKER_QDRANT_BINARY}" ]]; then
    echo "${ROOTSEEKER_QDRANT_BINARY}"
    return 0
  fi
  if command -v qdrant >/dev/null 2>&1; then
    command -v qdrant
    return 0
  fi
  for p in "$ROOT/tools/qdrant/qdrant" "$ROOT/tools/qdrant"; do
    if [[ -x "$p" ]]; then echo "$p"; return 0; fi
  done
  return 1
}

resolve_zoekt_web() {
  if [[ -n "${ROOTSEEKER_ZOEKT_WEBSERVER:-}" && -x "${ROOTSEEKER_ZOEKT_WEBSERVER}" ]]; then
    echo "${ROOTSEEKER_ZOEKT_WEBSERVER}"
    return 0
  fi
  if command -v zoekt-webserver >/dev/null 2>&1; then
    command -v zoekt-webserver
    return 0
  fi
  local gb
  gb="$(go_bin)"
  if [[ -n "$gb" && -x "$gb/zoekt-webserver" ]]; then
    echo "$gb/zoekt-webserver"
    return 0
  fi
  return 1
}

resolve_zoekt_index() {
  if [[ -n "${ROOTSEEKER_ZOEKT_INDEX_BINARY:-}" && -x "${ROOTSEEKER_ZOEKT_INDEX_BINARY}" ]]; then
    echo "${ROOTSEEKER_ZOEKT_INDEX_BINARY}"
    return 0
  fi
  if command -v zoekt-index >/dev/null 2>&1; then
    command -v zoekt-index
    return 0
  fi
  local gb
  gb="$(go_bin)"
  if [[ -n "$gb" && -x "$gb/zoekt-index" ]]; then
    echo "$gb/zoekt-index"
    return 0
  fi
  return 1
}

port_listening() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -i ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1
    return $?
  fi
  "$PYTHON" -c "import socket;s=socket.socket();import sys; r=s.connect_ex(('127.0.0.1',int(sys.argv[1]))); s.close(); sys.exit(0 if r==0 else 1)" "$port" 2>/dev/null
}

service_ok() {
  local name="$1"
  local url="$2"
  if command -v curl >/dev/null 2>&1; then
    if [[ "$url" == *"/api/list" ]]; then
      local code
      code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' -X POST "$url" -H 'Content-Type: application/json' -d '{}' || true)"
      [[ "$code" == "200" ]] && return 0
      code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' "$url" || true)"
      [[ "$code" == "200" ]] && return 0
      return 1
    fi
    [[ "$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' "$url" || true)" == "200" ]]
    return $?
  fi
  python3 - "$name" "$url" <<'PY' >/dev/null 2>&1
import socket
import sys
from urllib.parse import urlparse

url = urlparse(sys.argv[2])
s = socket.socket()
s.settimeout(3.0)
try:
    s.connect((url.hostname or "127.0.0.1", url.port or 80))
    sys.exit(0)
except Exception:
    sys.exit(1)
finally:
    s.close()
PY
}

QDRANT_BIN=""
if ! QDRANT_BIN="$(resolve_qdrant)"; then
  echo "错误: 未找到 qdrant 可执行文件。" >&2
  echo "  从 https://github.com/qdrant/qdrant/releases 下载并加入 PATH，或：" >&2
  echo "  export ROOTSEEKER_QDRANT_BINARY=/path/to/qdrant" >&2
  echo "若已安装 Docker 且希望用容器，可改用: ./scripts/start_zoekt_qdrant_docker.sh" >&2
  exit 1
fi

ZOEKT_WEB=""
if ! ZOEKT_WEB="$(resolve_zoekt_web)"; then
  echo "错误: 未找到 zoekt-webserver。" >&2
  echo "  go install github.com/sourcegraph/zoekt/cmd/zoekt-webserver@latest" >&2
  echo "  确保 \$(go env GOPATH)/bin 在 PATH 中。" >&2
  echo "若已安装 Docker，可改用: ./scripts/start_zoekt_qdrant_docker.sh" >&2
  exit 1
fi

ZOEKT_INDEX=""
if ! ZOEKT_INDEX="$(resolve_zoekt_index)"; then
  echo "错误: 未找到 zoekt-index。" >&2
  echo "  go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest" >&2
  echo "  或 export ROOTSEEKER_ZOEKT_INDEX_BINARY=/path/to/zoekt-index" >&2
  exit 1
fi
export ROOTSEEKER_ZOEKT_INDEX_BINARY="${ROOTSEEKER_ZOEKT_INDEX_BINARY:-$ZOEKT_INDEX}"

CFG="$ROOT/config/qdrant_config.yaml"
if [[ ! -f "$CFG" ]]; then
  echo "错误: 缺少 $CFG" >&2
  exit 1
fi

start_qdrant() {
  if port_listening 6333; then
    if service_ok qdrant "http://127.0.0.1:6333/collections"; then
      echo "Qdrant 端口 6333 已在监听且服务可用，跳过启动。"
      return 0
    fi
    echo "错误: 端口 6333 已被占用，但不是可用的 Qdrant (/collections 探测失败)。" >&2
    exit 1
  fi
  echo "启动 Qdrant: $QDRANT_BIN --config-path $CFG"
  nohup "$QDRANT_BIN" --config-path "$CFG" >>"$RUN_DIR/qdrant.log" 2>&1 &
  echo $! >"$RUN_DIR/qdrant.pid"
}

start_zoekt() {
  if port_listening 6070; then
    if service_ok zoekt "http://127.0.0.1:6070/api/list"; then
      echo "Zoekt 端口 6070 已在监听且服务可用，跳过启动。"
      return 0
    fi
    echo "错误: 端口 6070 已被占用，但不是可用的 Zoekt (/api/list 探测失败)。" >&2
    exit 1
  fi
  local idx="$ROOT/data/zoekt/index"
  echo "启动 Zoekt: $ZOEKT_WEB -index $idx -listen 127.0.0.1:6070 -rpc"
  nohup "$ZOEKT_WEB" -index "$idx" -listen "127.0.0.1:6070" -rpc >>"$RUN_DIR/zoekt.log" 2>&1 &
  echo $! >"$RUN_DIR/zoekt.pid"
}

start_qdrant
start_zoekt

echo "已尝试启动（若端口已占用则未重复启动）。日志: $RUN_DIR/qdrant.log , $RUN_DIR/zoekt.log"
echo "探测: $PYTHON scripts/smoke_zoekt_qdrant.py"
echo "停止: ./scripts/stop_zoekt_qdrant.sh"
