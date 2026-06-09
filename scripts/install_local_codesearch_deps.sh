#!/usr/bin/env bash
# 安装/检查无 Docker 代码索引依赖：Zoekt CLI + Qdrant 本机二进制。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== RootSeeker local code-search dependency check =="

if ! command -v go >/dev/null 2>&1; then
  echo "错误: 未找到 go。请先安装 Go 1.21+。" >&2
  exit 1
fi

echo "Go: $(go version)"
export PATH="$(go env GOPATH)/bin:$PATH"

if ! command -v zoekt-webserver >/dev/null 2>&1; then
  echo "安装 zoekt-webserver ..."
  go install github.com/sourcegraph/zoekt/cmd/zoekt-webserver@latest
else
  echo "zoekt-webserver: $(command -v zoekt-webserver)"
fi

if ! command -v zoekt-index >/dev/null 2>&1; then
  echo "安装 zoekt-index ..."
  go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest
else
  echo "zoekt-index: $(command -v zoekt-index)"
fi

if [[ -n "${ROOTSEEKER_QDRANT_BINARY:-}" && -x "${ROOTSEEKER_QDRANT_BINARY}" ]]; then
  echo "qdrant: ${ROOTSEEKER_QDRANT_BINARY}"
elif command -v qdrant >/dev/null 2>&1; then
  echo "qdrant: $(command -v qdrant)"
elif [[ -x "$ROOT/tools/qdrant/qdrant" ]]; then
  echo "qdrant: $ROOT/tools/qdrant/qdrant"
else
  cat >&2 <<'MSG'
未找到 qdrant 本机二进制。

请从 https://github.com/qdrant/qdrant/releases 下载与你系统匹配的压缩包，
解压后任选一种方式：
  1) 将 qdrant 放入 PATH
  2) 放到 tools/qdrant/qdrant
  3) export ROOTSEEKER_QDRANT_BINARY=/绝对路径/qdrant

Zoekt 已可通过 go install 安装；Qdrant 官方 release 文件名会随平台变化，因此这里不自动猜测下载 URL。
MSG
  exit 2
fi

echo ""
echo "完成。建议加入 shell profile:"
echo "  export PATH=\"$(go env GOPATH)/bin:\$PATH\""
echo ""
echo "下一步:"
echo "  ./scripts/start_zoekt_qdrant.sh"
echo "  ./scripts/run_real_codesearch_smoke.sh"
