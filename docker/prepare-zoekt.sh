#!/usr/bin/env bash
# Download Zoekt binaries on the host. Run before: docker compose build zoekt
set -euo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bin"
mkdir -p "$BIN_DIR"

VERSION="v0.0.0-2024-11-13"
BASE="https://github.com/sourcegraph/zoekt/releases/download/${VERSION}"
ARCH="linux_amd64"

for name in zoekt-webserver zoekt-index; do
  out="${BIN_DIR}/${name}"
  if [[ -f "$out" ]]; then
    echo "[skip] $name already exists"
    continue
  fi
  url="${BASE}/${name}_${ARCH}.tar.gz"
  tgz="$(mktemp)"
  echo "[download] $url"
  curl -fsSL -o "$tgz" "$url"
  tar -xzf "$tgz" -C "$BIN_DIR"
  rm -f "$tgz"
  chmod +x "$out"
  echo "[ok] $name"
done

echo "Zoekt binaries ready in $BIN_DIR"
