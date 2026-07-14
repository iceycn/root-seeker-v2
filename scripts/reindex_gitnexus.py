#!/usr/bin/env python3
"""Bulk-run GitNexus analyze over registered local clones (or a repos root)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from rootseeker.code_index.gitnexus_cli import GitNexusCliConfig
from rootseeker.code_index.gitnexus_indexer import GitNexusIndexer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reindex GitNexus graphs for local repos")
    parser.add_argument("--base-path", default=None, help="Repos root (default ROOTSEEKER_REPO_BASE_PATH/repos)")
    parser.add_argument("--repo", action="append", default=[], help="Only these repo directory names")
    parser.add_argument("--force", action="store_true", help="Pass --force to gitnexus analyze")
    args = parser.parse_args(argv)

    base = Path(args.base_path) if args.base_path else Path(os.getenv("ROOTSEEKER_REPO_BASE_PATH", "repos"))
    cfg = GitNexusCliConfig.from_env()
    if args.force:
        cfg.force_analyze = True
    indexer = GitNexusIndexer(config=cfg)

    targets: list[Path]
    if args.repo:
        targets = [base / name for name in args.repo]
    else:
        targets = sorted(p for p in base.iterdir() if p.is_dir() and (p / ".git").exists()) if base.exists() else []

    results = []
    for path in targets:
        status = indexer.index_repository(path.name, path, force=args.force)
        results.append(status.model_dump(mode="json"))
        print(json.dumps({"repo": path.name, "ready": status.ready, "detail": status.detail}, ensure_ascii=False))

    ok = sum(1 for item in results if item.get("ready"))
    print(json.dumps({"total": len(results), "ready": ok, "failed": len(results) - ok}, ensure_ascii=False))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
