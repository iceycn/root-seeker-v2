#!/usr/bin/env python3
"""探测 Zoekt / Qdrant 是否可访问（环境与 root_seek/config.yaml 语义对齐）。

用法:
  python3 scripts/smoke_zoekt_qdrant.py
  python3 scripts/smoke_zoekt_qdrant.py --only zoekt
  python3 scripts/smoke_zoekt_qdrant.py --no-strict   # 失败仍返回 0

与 root_seek 对应关系:
  zoekt.api_base_url -> ZOEKT_ENDPOINT 或 ROOTSEEKER_ZOEKT_ENDPOINT
  qdrant.url         -> QDRANT_ENDPOINT 或 ROOTSEEKER_QDRANT_ENDPOINT
  qdrant.collection  -> QDRANT_COLLECTION_NAME 或 ROOTSEEKER_QDRANT_COLLECTION_NAME

完整联调（本机二进制，无 Docker）：`./scripts/start_zoekt_qdrant.sh` 后索引，或一键 `./scripts/run_real_codesearch_smoke.sh`。若使用 Docker 见 `scripts/start_zoekt_qdrant_docker.sh`。

需本机或网络内已启动 Zoekt Web（通常 :6070）与 Qdrant（通常 :6333）。
"""

from __future__ import annotations

import argparse
import os
import sys


def _zoekt_base() -> str:
    return (
        (os.getenv("ZOEKT_ENDPOINT") or "").strip()
        or (os.getenv("ROOTSEEKER_ZOEKT_ENDPOINT") or "").strip()
        or "http://127.0.0.1:6070"
    ).rstrip("/")


def _qdrant_base() -> str:
    return (
        (os.getenv("QDRANT_ENDPOINT") or "").strip()
        or (os.getenv("ROOTSEEKER_QDRANT_ENDPOINT") or "").strip()
        or "http://127.0.0.1:6333"
    ).rstrip("/")


def _qdrant_headers() -> dict[str, str]:
    key = (os.getenv("QDRANT_API_KEY") or os.getenv("ROOTSEEKER_QDRANT_API_KEY") or "").strip()
    return {"api-key": key} if key else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Zoekt/Qdrant connectivity smoke test")
    parser.add_argument(
        "--only",
        choices=("zoekt", "qdrant", "both"),
        default="both",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="任一端失败时仍返回退出码 0（仅打印结果）",
    )
    args = parser.parse_args()

    import httpx

    z_base = _zoekt_base()
    q_base = _qdrant_base()
    print(f"Zoekt base URL: {z_base}")
    print(f"Qdrant base URL: {q_base}")

    ok = True
    if args.only in ("zoekt", "both"):
        try:
            r = httpx.post(f"{z_base}/api/list", json={}, timeout=10.0, trust_env=False)
            if r.status_code == 405:
                r = httpx.get(f"{z_base}/api/list", timeout=10.0, trust_env=False)
            print(f"Zoekt /api/list -> HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                lst = data.get("List") or {}
                n = len(lst.get("Repos") or [])
                if n == 0:
                    n = len(data.get("RepoList") or [])
                print(f"  indexed repos: {n}")
            else:
                print(f"  response body (truncated): {r.text[:400]}")
                ok = False
        except httpx.HTTPError as e:
            print(f"Zoekt request failed: {e}")
            ok = False

    if args.only in ("qdrant", "both"):
        try:
            r = httpx.get(
                f"{q_base}/collections",
                headers=_qdrant_headers(),
                timeout=10.0,
                trust_env=False,
            )
            print(f"Qdrant GET /collections -> HTTP {r.status_code}")
            if r.status_code == 200:
                cols = r.json().get("result", {}).get("collections", [])
                names = [c.get("name", "?") for c in cols]
                print(f"  collections ({len(names)}): {names[:20]}{'...' if len(names) > 20 else ''}")
            else:
                print(f"  response body (truncated): {r.text[:400]}")
                ok = False
        except httpx.HTTPError as e:
            print(f"Qdrant request failed: {e}")
            ok = False

    if args.no_strict:
        return 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
