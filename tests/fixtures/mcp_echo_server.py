"""Minimal stdio MCP server for unit tests — exposes echo tool (newline-delimited JSON)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _read_message() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        return None
    stripped = line.strip()
    if not stripped:
        return _read_message()
    return json.loads(stripped)


def _write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    while True:
        request = _read_message()
        if request is None:
            break
        method = str(request.get("method") or "")
        req_id = request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "echo-fixture", "version": "0.1.0"},
                    },
                }
            )
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Echo input text",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"message": {"type": "string"}},
                                },
                            },
                            {
                                "name": "echo_env",
                                "description": "Echo an environment variable",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"key": {"type": "string"}},
                                },
                            },
                        ]
                    },
                }
            )
            continue

        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if name == "echo_env":
                key = str(arguments.get("key") or "")
                text = os.environ.get(key, "")
            elif name == "echo":
                text = str(arguments.get("message") or "")
            else:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"unknown tool: {name}"},
                    }
                )
                continue
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "isError": False,
                    },
                }
            )
            continue

        if req_id is not None:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"unknown method: {method}"},
                }
            )


if __name__ == "__main__":
    main()
