#!/usr/bin/env bash
# RootSeeker V2 国内安装入口：Docker / 下载走国内加速源
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export ROOTSEEKER_SETUP_REGION=cn
echo "[信息] 使用国内加速安装脚本 (setup-cn.sh)"

exec "$SCRIPT_DIR/setup.sh" "$@"
