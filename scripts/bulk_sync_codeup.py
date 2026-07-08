"""Bulk sync all Codeup repos registered in Admin."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"
LOG = Path("/app/data/bulk-import-codeup.log")


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def main() -> int:
    repos = httpx.get(f"{BASE}/api/repos", timeout=60).json().get("repos", [])
    codeup = [
        repo
        for repo in repos
        if repo.get("metadata", {}).get("remote_name") == "codeup"
        or "6183d17ff1ae9b61971d96b5" in repo.get("name", "")
    ]
    todo = [repo for repo in codeup if repo.get("sync_status", {}).get("state") != "completed"]
    log(f"Start bulk sync: {len(todo)} repos pending (total codeup: {len(codeup)})")

    ok = 0
    fail = 0
    for index, repo in enumerate(todo, 1):
        name = repo["name"]
        short = name.split("__")[-1]
        try:
            response = httpx.post(
                f"{BASE}/api/repos/{name}/sync",
                json={"trigger_index": True, "force_reclone": False},
                timeout=600,
            )
            payload = response.json() if response.content else {}
            if response.status_code < 400 and payload.get("ok", True):
                ok += 1
                log(f"[{index}/{len(todo)}] OK {short}")
            else:
                fail += 1
                detail = payload.get("detail") or response.text[:150]
                log(f"[{index}/{len(todo)}] FAIL {short}: {response.status_code} {detail}")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            log(f"[{index}/{len(todo)}] ERROR {short}: {str(exc)[:150]}")

    log(f"Finished: ok={ok}, fail={fail}, total={len(todo)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
