"""Synchronous stdio transport client for MCP (newline-delimited JSON-RPC)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

__all__ = ["McpStdioSession", "McpStdioSessionError", "normalize_tool_call_result"]


class McpStdioSessionError(Exception):
    """Raised when stdio MCP session fails."""


def _spawn_stdio_process(
    command: str,
    args: list[str],
    *,
    env: dict[str, str],
    cwd: str | None,
) -> subprocess.Popen[bytes]:
    executable = shutil.which(command) or command
    merged_env = os.environ.copy()
    merged_env.update(env)
    stderr_target: Any = subprocess.PIPE
    if sys.platform == "win32":
        node_path = shutil.which("node")
        if node_path:
            node_dir = os.path.dirname(node_path)
            path_value = merged_env.get("PATH", "")
            if node_dir.lower() not in path_value.lower():
                merged_env["PATH"] = node_dir + os.pathsep + path_value
        if str(executable).lower().endswith((".cmd", ".bat")):
            cmd_line = subprocess.list2cmdline([executable, *args])
            return subprocess.Popen(
                cmd_line,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_target,
                env=merged_env,
                cwd=cwd,
            )
    return subprocess.Popen(
        [executable, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_target,
        env=merged_env,
        cwd=cwd,
    )


def normalize_tool_call_result(result: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    """Convert MCP tools/call result into a gateway-friendly content dict."""
    content_blocks = result.get("content")
    if not isinstance(content_blocks, list):
        content_blocks = []
    texts: list[str] = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(str(block.get("text") or ""))
    return {
        "ok": not bool(result.get("isError")),
        "tool": tool_name,
        "text": "\n".join(texts),
        "content": content_blocks,
        "structuredContent": result.get("structuredContent"),
        "isError": bool(result.get("isError")),
    }


class McpStdioSession:
    def __init__(
        self,
        command: str,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._command = command.strip()
        self._args = list(args)
        self._env = dict(env or {})
        self._cwd = cwd.strip() if cwd else None
        self._timeout_seconds = timeout_seconds
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._initialized = False
        self._stderr_tail = ""
        self._stderr_thread: threading.Thread | None = None

    def connect(self) -> None:
        if self._proc is not None:
            return
        if not self._command:
            raise McpStdioSessionError("command is required for stdio transport")
        merged_env = os.environ.copy()
        merged_env.update(self._env)
        try:
            self._proc = _spawn_stdio_process(
                self._command,
                self._args,
                env=merged_env,
                cwd=self._cwd,
            )
        except OSError as exc:
            raise McpStdioSessionError(f"failed to spawn MCP process: {exc}") from exc
        self._initialized = False
        self._stderr_tail = ""
        if self._proc.stderr is not None:
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(self._proc.stderr,),
                name="mcp-stdio-stderr",
                daemon=True,
            )
            self._stderr_thread.start()

    def _drain_stderr(self, stderr: Any) -> None:
        chunks: list[str] = []
        while True:
            data = stderr.read(4096)
            if not data:
                break
            chunks.append(data.decode("utf-8", errors="replace"))
            combined = "".join(chunks)
            if len(combined) > 8192:
                combined = combined[-8192:]
                chunks = [combined]
            self._stderr_tail = combined

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
        self._proc = None
        self._initialized = False

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            return []
        return [item for item in tools if isinstance(item, dict)]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._request("tools/call", {"name": name, "arguments": dict(arguments)})
        if not isinstance(result, dict):
            return normalize_tool_call_result({}, tool_name=name)
        return normalize_tool_call_result(result, tool_name=name)

    def _request(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        with self._lock:
            self.connect()
            if not self._initialized:
                self._request_unlocked(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "rootseeker", "version": "0.1.0"},
                    },
                )
                self._write_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self._initialized = True
            return self._request_unlocked(method, params)

    def _request_unlocked(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write_message(payload)
        while True:
            response = self._read_message_with_timeout()
            if response.get("id") == msg_id:
                if "error" in response:
                    error = response["error"]
                    message = error.get("message") if isinstance(error, dict) else str(error)
                    raise McpStdioSessionError(str(message or "MCP request failed"))
                result = response.get("result")
                return result if isinstance(result, dict) else {}

    def _read_message(self) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise McpStdioSessionError("MCP process is not connected")
        while True:
            line = proc.stdout.readline()
            if not line:
                detail = self._stderr_tail.strip() or "stdout closed"
                raise McpStdioSessionError(f"MCP process ended: {detail}")
            stripped = line.decode("utf-8", errors="replace").strip()
            if not stripped:
                continue
            if stripped.startswith("{"):
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
                raise McpStdioSessionError("invalid MCP JSON response")
            if stripped.lower().startswith("content-length:"):
                return self._read_content_length_message(stripped, proc.stdout)
            if ":" not in stripped:
                # Some MCP servers print a startup banner before framed messages.
                continue
            raise McpStdioSessionError(f"unexpected MCP stdout line: {stripped}")

    def _read_content_length_message(
        self,
        first_header_line: str,
        stdout: Any,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        key, value = first_header_line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
        while True:
            line = stdout.readline()
            if not line:
                detail = self._stderr_tail.strip() or "stdout closed"
                raise McpStdioSessionError(f"MCP process ended: {detail}")
            stripped = line.decode("utf-8", errors="replace").strip()
            if not stripped:
                break
            if ":" in stripped:
                header_key, header_value = stripped.split(":", 1)
                headers[header_key.strip().lower()] = header_value.strip()
        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise McpStdioSessionError("missing Content-Length in MCP response")
        body = stdout.read(content_length)
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise McpStdioSessionError("invalid MCP JSON response")
        return parsed

    def _read_message_with_timeout(self) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._read_message)
            try:
                return future.result(timeout=self._timeout_seconds)
            except FuturesTimeoutError:
                self.close()
                raise McpStdioSessionError(
                    f"MCP response timed out after {self._timeout_seconds}s"
                ) from None

    def _write_message(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise McpStdioSessionError("MCP process is not connected")
        payload = json.dumps(message, ensure_ascii=False) + "\n"
        proc.stdin.write(payload.encode("utf-8"))
        proc.stdin.flush()
