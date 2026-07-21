#!/usr/bin/env bash
# RootSeeker V2 首次安装向导（macOS / Linux）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PY="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[错误] 未找到 python3/python，请先安装 Python 3.11+"
  exit 1
fi

exec "$PY" "$SCRIPT_DIR/scripts/setup_wizard.py" "$@"
