#!/usr/bin/env python3
"""Zoekt + Qdrant 真机联调：需本机已启动 Zoekt/Qdrant（参见 scripts/start_zoekt_qdrant.sh）。

检查项：
  1) Zoekt POST /api/list（旧版回退 GET）
  2) （可选）Zoekt POST /api/search 是否有命中
  3) Qdrant 列出 collections，并对 code_chunks 执行 ensure_collection
"""

from __future__ import annotations

import argparse
import os
import sys


def _z_base() -> str:
    return (
        (os.getenv("ZOEKT_ENDPOINT") or "").strip()
        or (os.getenv("ROOTSEEKER_ZOEKT_ENDPOINT") or "").strip()
        or "http://127.0.0.1:6070"
    ).rstrip("/")


def _q_base() -> str:
    return (
        (os.getenv("QDRANT_ENDPOINT") or "").strip()
        or (os.getenv("ROOTSEEKER_QDRANT_ENDPOINT") or "").strip()
        or "http://127.0.0.1:6333"
    ).rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expect-zoekt-hits",
        action="store_true",
        help="要求 /api/search 至少 1 条命中（需已索引 data/repos/smoke_mini）",
    )
    args = parser.parse_args()

    import httpx

    z = _z_base()
    ok = True
    print(f"Zoekt: {z}", flush=True)

    try:
        r = httpx.post(f"{z}/api/list", json={}, timeout=15.0, trust_env=False)
        if r.status_code == 405:
            r = httpx.get(f"{z}/api/list", timeout=15.0, trust_env=False)
        print(f"  /api/list -> HTTP {r.status_code}", flush=True)
        if r.status_code != 200:
            ok = False
            print(f"  body: {r.text[:400]}", flush=True)
        else:
            data = r.json()
            lst = data.get("List") or {}
            n = len(lst.get("Repos") or [])
            if n == 0:
                n = len(data.get("RepoList") or [])
            print(f"  repos: {n}", flush=True)
    except httpx.HTTPError as e:
        print(f"  Zoekt 不可达: {e}", flush=True)
        return 2

    if args.expect_zoekt_hits:
        try:
            r = httpx.post(
                f"{z}/api/search",
                json={"q": "readme", "Num": 10},
                timeout=15.0,
                trust_env=False,
            )
            if r.status_code == 405:
                r = httpx.get(
                    f"{z}/api/search",
                    params={"q": "readme", "num": "10"},
                    timeout=15.0,
                    trust_env=False,
                )
            print(f"  /api/search q=readme -> HTTP {r.status_code}", flush=True)
            data = r.json() if r.status_code == 200 else {}
            hits = 0
            res = data.get("Result")
            if isinstance(res, dict) and "Files" in res:
                for fm in res.get("Files") or []:
                    hits += len(fm.get("LineMatches") or [])
            elif isinstance(res, list):
                for item in res:
                    for fm in item.get("FileMatches") or []:
                        hits += len(fm.get("LineMatches") or [])
            print(f"  LineMatches 条数 (粗略): {hits}", flush=True)
            if r.status_code != 200 or hits < 1:
                print(
                    "  错误: 未检索到命中。请对索引目录执行 zoekt-index（见 run_real_codesearch_smoke.sh）。",
                    flush=True,
                )
                ok = False
        except httpx.HTTPError as e:
            print(f"  search 失败: {e}", flush=True)
            ok = False

    q = _q_base()
    print(f"Qdrant: {q}", flush=True)
    try:
        r = httpx.get(f"{q}/collections", timeout=15.0, trust_env=False)
        print(f"  GET /collections -> HTTP {r.status_code}", flush=True)
        if r.status_code != 200:
            ok = False
            print(f"  body: {r.text[:400]}", flush=True)
    except httpx.HTTPError as e:
        print(f"  Qdrant 不可达: {e}", flush=True)
        return 3

    from rootseeker.code_index.qdrant_indexer import QdrantIndexer

    qix = QdrantIndexer(endpoint=q)
    ensured = qix.ensure_collection()
    print(
        f"  ensure_collection('{qix.collection_name}'): {'ok' if ensured else 'FAILED'}",
        flush=True,
    )
    if not ensured:
        ok = False

    status = qix.get_status()
    print(
        f"  collection status.detail keys: {list((status.detail or {}).keys())[:8]}",
        flush=True,
    )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
