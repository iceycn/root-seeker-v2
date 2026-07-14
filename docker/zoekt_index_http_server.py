#!/usr/bin/env python3
"""Thin HTTP wrapper around ``zoekt-index`` for RootSeeker remote indexing.

POST /v1/index  { "path": "/repos/foo", "index_dir"?: "/data/index", "timeout_seconds"?: 600 }
GET  /healthz
"""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = os.environ.get("ZOEKT_INDEX_HTTP_HOST", "0.0.0.0")
PORT = int(os.environ.get("ZOEKT_INDEX_HTTP_PORT", "6071"))
DEFAULT_INDEX_DIR = os.environ.get("ZOEKT_INDEX_DIR", "/data/index")
DEFAULT_TIMEOUT = float(os.environ.get("ZOEKT_INDEX_HTTP_TIMEOUT_SECONDS", "600"))
BINARY = os.environ.get("ZOEKT_INDEX_BINARY", "/usr/local/bin/zoekt-index")


def _run_index(path: str, index_dir: str, timeout_seconds: float) -> dict:
    cmd = [BINARY, "-index", index_dir, path]
    try:
        Path(index_dir).mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": (result.stdout or "")[-8000:],
            "stderr": (result.stderr or "")[-8000:],
            "command": cmd,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[-8000:],
            "stderr": f"zoekt-index timed out after {timeout_seconds}s",
            "command": cmd,
        }
    except OSError as exc:
        return {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "command": cmd,
        }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/healthz", "/"}:
            self._send_json(200, {"ok": True, "service": "zoekt-index-http"})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/v1/index":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid json"})
            return
        repo_path = str(payload.get("path") or "").strip()
        if not repo_path:
            self._send_json(400, {"ok": False, "error": "path is required"})
            return
        if not Path(repo_path).exists():
            self._send_json(400, {"ok": False, "error": f"path does not exist: {repo_path}"})
            return
        index_dir = str(payload.get("index_dir") or DEFAULT_INDEX_DIR).strip() or DEFAULT_INDEX_DIR
        timeout_raw = payload.get("timeout_seconds")
        try:
            timeout_seconds = float(timeout_raw) if timeout_raw is not None else DEFAULT_TIMEOUT
        except (TypeError, ValueError):
            timeout_seconds = DEFAULT_TIMEOUT
        result = _run_index(repo_path, index_dir, timeout_seconds)
        self._send_json(200 if result["ok"] else 500, result)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"zoekt-index-http listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
