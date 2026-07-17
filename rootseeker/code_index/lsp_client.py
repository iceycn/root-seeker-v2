from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

__all__ = [
    "LspClient",
    "LspPosition",
    "LspRange",
    "LspLocation",
    "LspSymbolInfo",
    "LspClientConfig",
    "LspServerType",
]

logger = logging.getLogger(__name__)


class LspServerType(StrEnum):
    """支持的 LSP 服务器类型"""

    PYRIGHT = "pyright"
    PYLSP = "pylsp"
    GOPALS = "gopls"
    TYPESCRIPT = "typescript-language-server"
    RUST_ANALYZER = "rust-analyzer"
    JAVA_JDTLS = "jdtls"
    GENERIC = "generic"


@dataclass
class LspPosition:
    """LSP 位置"""

    line: int
    character: int

    def to_dict(self) -> dict:
        return {"line": self.line, "character": self.character}


@dataclass
class LspRange:
    """LSP 范围"""

    start: LspPosition
    end: LspPosition

    def to_dict(self) -> dict:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass
class LspLocation:
    """LSP 位置（文件 + 范围）"""

    uri: str
    range: LspRange

    def to_dict(self) -> dict:
        return {"uri": self.uri, "range": self.range.to_dict()}


@dataclass
class LspSymbolInfo:
    """符号信息"""

    name: str
    kind: int
    location: LspLocation
    container_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "containerName": self.container_name,
        }


@dataclass
class LspClientConfig:
    """LSP 客户端配置"""

    server_type: LspServerType = LspServerType.PYRIGHT
    server_command: list[str] | None = None
    server_path: str | None = None
    initialization_options: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0

    def get_server_command(self) -> list[str]:
        if self.server_command:
            return self.server_command

        defaults = {
            LspServerType.PYRIGHT: ["pyright-langserver", "--stdio"],
            LspServerType.PYLSP: ["pylsp"],
            LspServerType.GOPALS: ["gopls"],
            LspServerType.TYPESCRIPT: ["typescript-language-server", "--stdio"],
            LspServerType.RUST_ANALYZER: ["rust-analyzer"],
            LspServerType.JAVA_JDTLS: ["jdtls"],
        }
        return defaults.get(self.server_type, ["pyright-langserver", "--stdio"])


class LspClient:
    """LSP 客户端 - 与 Language Server 通信"""

    def __init__(self, config: LspClientConfig | None = None) -> None:
        self.config = config or LspClientConfig()
        self._process: subprocess.Popen | None = None
        self._request_id: int = 0
        self._initialized: bool = False
        self._root_uri: str | None = None

    def start(self) -> bool:
        """启动 LSP 服务器进程"""
        if self._process is not None:
            return True

        cmd = self.config.get_server_command()
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
            )
            logger.info(f"Started LSP server: {' '.join(cmd)}")
            return True
        except FileNotFoundError as e:
            logger.error(f"LSP server not found: {e}")
            return False

    def stop(self) -> None:
        """停止 LSP 服务器"""
        if self._process:
            self._process.terminate()
            self._process = None
            self._initialized = False
            logger.info("LSP server stopped")

    def _send_request(self, method: str, params: dict | None = None) -> dict | None:
        """发送 JSON-RPC 请求"""
        if not self._process:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        content = json.dumps(request)
        header = f"Content-Length: {len(content)}\r\n\r\n"

        try:
            self._process.stdin.write(header + content)
            self._process.stdin.flush()
            return self._read_response()
        except Exception as e:
            logger.error(f"LSP request failed: {e}")
            return None

    def _read_response(self) -> dict | None:
        """读取 JSON-RPC 响应"""
        if not self._process:
            return None

        try:
            # 读取 header
            headers = {}
            while True:
                line = self._process.stdout.readline()
                if line == "\r\n" or line == "":
                    break
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip()] = value.strip()

            length = int(headers.get("Content-Length", 0))
            if length == 0:
                return None

            # 读取 content
            content = self._process.stdout.read(length)
            return json.loads(content)
        except Exception as e:
            logger.error(f"LSP response read failed: {e}")
            return None

    def initialize(self, root_path: str) -> bool:
        """初始化 LSP 连接"""
        if self._initialized:
            return True

        if not self.start():
            return False

        self._root_uri = Path(root_path).as_uri()
        params = {
            "processId": os.getpid(),
            "rootUri": self._root_uri,
            "capabilities": {
                "textDocument": {
                    "definition": {"linkSupport": True},
                    "references": {"linkSupport": True},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                },
            },
            "initializationOptions": self.config.initialization_options,
        }

        response = self._send_request("initialize", params)
        if response and "result" in response:
            self._initialized = True
            self._send_notification("initialized", {})
            logger.info(f"LSP initialized for {root_path}")
            return True

        logger.error("LSP initialization failed")
        return False

    def _send_notification(self, method: str, params: dict | None = None) -> None:
        """发送 JSON-RPC 通知（无响应）"""
        if not self._process:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        content = json.dumps(notification)
        header = f"Content-Length: {len(content)}\r\n\r\n"

        try:
            self._process.stdin.write(header + content)
            self._process.stdin.flush()
        except Exception as e:
            logger.error(f"LSP notification failed: {e}")

    def open_document(self, file_path: str, content: str | None = None) -> None:
        """打开文档"""
        uri = Path(file_path).as_uri()
        if content is None:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except Exception:
                content = ""

        params = {
            "textDocument": {
                "uri": uri,
                "languageId": self._detect_language(file_path),
                "version": 1,
                "text": content,
            }
        }
        self._send_notification("textDocument/didOpen", params)

    def _detect_language(self, file_path: str) -> str:
        """检测文件语言"""
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".jsx": "javascriptreact",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".kt": "kotlin",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
        }
        return mapping.get(ext, "plaintext")

    def find_references(
        self,
        file_path: str,
        line: int,
        character: int,
        include_declaration: bool = True,
    ) -> list[LspLocation]:
        """查找符号引用"""
        uri = Path(file_path).as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration},
        }

        response = self._send_request("textDocument/references", params)
        if not response or "result" not in response:
            return []

        results = []
        for item in response.get("result", []) or []:
            if "uri" in item and "range" in item:
                loc = self._parse_location(item)
                if loc:
                    results.append(loc)
        return results

    def go_to_definition(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[LspLocation]:
        """跳转到定义"""
        uri = Path(file_path).as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }

        response = self._send_request("textDocument/definition", params)
        if not response or "result" not in response:
            return []

        result = response.get("result")
        if result is None:
            return []

        # 处理单个 Location 或 LocationLink
        if isinstance(result, dict):
            loc = self._parse_location(result)
            return [loc] if loc else []

        # 处理数组
        results = []
        for item in result:
            loc = self._parse_location(item)
            if loc:
                results.append(loc)
        return results

    def _parse_location(self, item: dict) -> LspLocation | None:
        """解析 LSP Location"""
        try:
            uri = item.get("uri", "")
            range_data = item.get("range", {})
            start = range_data.get("start", {})
            end = range_data.get("end", {})

            return LspLocation(
                uri=uri,
                range=LspRange(
                    start=LspPosition(
                        line=start.get("line", 0), character=start.get("character", 0)
                    ),
                    end=LspPosition(line=end.get("line", 0), character=end.get("character", 0)),
                ),
            )
        except Exception:
            return None

    def hover(self, file_path: str, line: int, character: int) -> str | None:
        """获取悬停信息"""
        uri = Path(file_path).as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }

        response = self._send_request("textDocument/hover", params)
        if not response or "result" not in response:
            return None

        result = response.get("result")
        if not result:
            return None

        contents = result.get("contents")
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            return contents.get("value", "")
        if isinstance(contents, list):
            return "\n".join(
                c.get("value", str(c)) if isinstance(c, dict) else str(c) for c in contents
            )
        return None

    def document_symbols(self, file_path: str) -> list[LspSymbolInfo]:
        """获取文档符号列表"""
        uri = Path(file_path).as_uri()
        params = {"textDocument": {"uri": uri}}

        response = self._send_request("textDocument/documentSymbol", params)
        if not response or "result" not in response:
            return []

        results = []
        for item in response.get("result", []) or []:
            symbol = self._parse_symbol(item)
            if symbol:
                results.append(symbol)
        return results

    def _parse_symbol(self, item: dict) -> LspSymbolInfo | None:
        """解析符号信息"""
        try:
            name = item.get("name", "")
            kind = item.get("kind", 0)
            location_data = item.get("location", {})
            container = item.get("containerName")

            loc = self._parse_location(location_data)
            if not loc:
                return None

            return LspSymbolInfo(
                name=name,
                kind=kind,
                location=loc,
                container_name=container,
            )
        except Exception:
            return None

    def __enter__(self) -> LspClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
