#!/usr/bin/env bash
# RootSeeker 卸载：停止 Docker/本机进程，并清理全部安装产物
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -n "${ROOTSEEKER_UNINSTALL_PYTHON:-}" && -x "$ROOTSEEKER_UNINSTALL_PYTHON" ]]; then
  PY="$ROOTSEEKER_UNINSTALL_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PY="$SCRIPT_DIR/.venv/bin/python"
else
  echo "[错误] 未找到 python3/python，请先安装 Python 3.11+"
  exit 1
fi

echo "[信息] 开始卸载（将删除 .env / .venv / .tools / data / Docker volumes 等）"
exec "$PY" "$SCRIPT_DIR/scripts/uninstall.py" "$@"
