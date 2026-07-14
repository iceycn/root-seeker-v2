"""Reindex all Admin-registered repos into Qdrant using symbol-aware chunking.

Skips git sync; reads local clones and calls QdrantIndexer.index_chunks only.

Usage (host, with repo base already local):
  python scripts/reindex_qdrant_symbol_chunks.py

Usage (Docker volume + compose network):
  docker run --rm \\
    --network <compose_network> \\
    -v root-seeker-v2_repo-data:/data/repos:ro \\
    -v %CD%:/app -w /app \\
    -e PYTHONPATH=/app \\
    -e ROOTSEEKER_QDRANT_ENDPOINT=http://qdrant:6333 \\
    -e ROOTSEEKER_REPO_BASE_PATH=/data/repos \\
    -e ROOTSEEKER_EMBEDDING_PROVIDER=hash \\
    python:3.12-slim \\
    bash -lc "pip install -q -e . && python scripts/reindex_qdrant_symbol_chunks.py"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_repos(admin_url: str) -> list[dict]:
    response = httpx.get(f"{admin_url.rstrip('/')}/api/repos", timeout=60.0)
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("repos") or [])


def _resolve_local_path(repo: dict, base_path: Path) -> Path | None:
    name = str(repo.get("name") or "")
    raw = str(repo.get("local_path") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
        # Admin often stores container paths like /data/repos/<name>
        if raw.startswith("/data/repos/"):
            candidates.append(base_path / Path(raw).name)
        if raw.startswith("/repos/"):
            candidates.append(base_path / Path(raw).name)
    if name:
        candidates.append(base_path / name)
    for path in candidates:
        if path.is_dir():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", default=os.getenv("ROOTSEEKER_ADMIN_URL", "http://127.0.0.1:8010"))
    parser.add_argument(
        "--repo-base",
        default=os.getenv("ROOTSEEKER_REPO_BASE_PATH", "repos"),
        help="Local/container directory that contains cloned repos",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional max repos to process (0=all)")
    parser.add_argument("--only", action="append", default=[], help="Only reindex these repo names")
    parser.add_argument(
        "--report",
        default=str(ROOT / "data" / "tmp-qdrant-reindex-report.json"),
        help="Write JSON report path",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from rootseeker.code_index.chunker import chunk_code_files
    from rootseeker.code_index.file_scanner import scan_code_files
    from rootseeker.code_index.qdrant_indexer import QdrantIndexer

    base_path = Path(args.repo_base)
    repos = _load_repos(args.admin_url)
    if args.only:
        only = set(args.only)
        repos = [repo for repo in repos if repo.get("name") in only]
    if args.limit and args.limit > 0:
        repos = repos[: args.limit]

    indexer = QdrantIndexer()
    _log(
        f"reindex start: repos={len(repos)} base={base_path} "
        f"qdrant={indexer.endpoint} collection={indexer.collection_name}"
    )

    report: dict = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(repos),
        "ok": 0,
        "skip": 0,
        "fail": 0,
        "results": [],
    }

    for index, repo in enumerate(repos, 1):
        name = str(repo.get("name") or "")
        local = _resolve_local_path(repo, base_path)
        if local is None:
            report["skip"] += 1
            report["results"].append({"name": name, "status": "skip", "reason": "local path missing"})
            _log(f"[{index}/{len(repos)}] SKIP {name}: local path missing")
            continue
        try:
            started = time.perf_counter()
            files = scan_code_files(local)
            chunks = chunk_code_files(name, files)
            with_symbol = sum(1 for chunk in chunks if chunk.symbol)
            status = indexer.index_chunks(name, chunks)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            row = {
                "name": name,
                "status": "ok" if status.ready else "fail",
                "path": str(local),
                "files": len(files),
                "chunks": len(chunks),
                "chunks_with_symbol": with_symbol,
                "elapsed_ms": elapsed_ms,
                "detail": status.detail,
            }
            if status.ready:
                report["ok"] += 1
                _log(
                    f"[{index}/{len(repos)}] OK {name}: files={len(files)} "
                    f"chunks={len(chunks)} symbol={with_symbol} ({elapsed_ms}ms)"
                )
            else:
                report["fail"] += 1
                row["reason"] = str((status.detail or {}).get("error") or "index not ready")
                _log(f"[{index}/{len(repos)}] FAIL {name}: {row['reason']}")
            report["results"].append(row)
        except Exception as exc:  # noqa: BLE001
            report["fail"] += 1
            report["results"].append({"name": name, "status": "fail", "reason": str(exc)})
            _log(f"[{index}/{len(repos)}] FAIL {name}: {type(exc).__name__}: {exc}")

    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(
        f"reindex done: ok={report['ok']} skip={report['skip']} fail={report['fail']} "
        f"report={report_path}"
    )
    return 0 if report["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
