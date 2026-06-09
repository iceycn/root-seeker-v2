from __future__ import annotations

import logging
import os
from pathlib import Path

from rootseeker.code_index.lsp_client import (
    LspClient,
    LspClientConfig,
    LspLocation,
    LspServerType,
)

__all__ = [
    "find_symbol_references",
    "go_to_definition",
    "get_hover_info",
    "get_document_symbols",
    "LspToolsService",
]

logger = logging.getLogger(__name__)


class LspToolsService:
    """LSP 工具服务 - 管理多个 LSP 客户端"""

    def __init__(self, default_root: str | None = None) -> None:
        self._clients: dict[str, LspClient] = {}
        self._default_root = default_root or os.getcwd()

    def get_client(
        self,
        root_path: str,
        server_type: LspServerType = LspServerType.PYRIGHT,
    ) -> LspClient | None:
        """获取或创建 LSP 客户端"""
        key = f"{root_path}:{server_type.value}"

        if key not in self._clients:
            config = LspClientConfig(server_type=server_type)
            client = LspClient(config)
            if client.initialize(root_path):
                self._clients[key] = client
            else:
                logger.error(f"Failed to initialize LSP client for {root_path}")
                return None

        return self._clients.get(key)

    def find_references(
        self,
        file_path: str,
        line: int,
        character: int,
        root_path: str | None = None,
    ) -> list[dict]:
        """查找符号引用"""
        root = root_path or self._detect_root(file_path) or self._default_root
        client = self.get_client(root)
        if not client:
            return []

        client.open_document(file_path)
        locations = client.find_references(file_path, line, character)
        return [self._location_to_dict(loc) for loc in locations]

    def go_to_definition(
        self,
        file_path: str,
        line: int,
        character: int,
        root_path: str | None = None,
    ) -> list[dict]:
        """跳转到定义"""
        root = root_path or self._detect_root(file_path) or self._default_root
        client = self.get_client(root)
        if not client:
            return []

        client.open_document(file_path)
        locations = client.go_to_definition(file_path, line, character)
        return [self._location_to_dict(loc) for loc in locations]

    def get_hover(
        self,
        file_path: str,
        line: int,
        character: int,
        root_path: str | None = None,
    ) -> str | None:
        """获取悬停信息"""
        root = root_path or self._detect_root(file_path) or self._default_root
        client = self.get_client(root)
        if not client:
            return None

        client.open_document(file_path)
        return client.hover(file_path, line, character)

    def get_symbols(
        self,
        file_path: str,
        root_path: str | None = None,
    ) -> list[dict]:
        """获取文档符号列表"""
        root = root_path or self._detect_root(file_path) or self._default_root
        client = self.get_client(root)
        if not client:
            return []

        client.open_document(file_path)
        symbols = client.document_symbols(file_path)
        return [s.to_dict() for s in symbols]

    def _detect_root(self, file_path: str) -> str | None:
        """检测项目根目录"""
        path = Path(file_path).resolve()
        markers = [".git", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml", "package.json"]

        for parent in path.parents:
            for marker in markers:
                if (parent / marker).exists():
                    return str(parent)
        return None

    def _location_to_dict(self, loc: LspLocation) -> dict:
        """转换位置为字典"""
        return {
            "uri": loc.uri,
            "path": loc.uri.replace("file://", ""),
            "range": loc.range.to_dict(),
            "line": loc.range.start.line,
            "character": loc.range.start.character,
        }

    def close_all(self) -> None:
        """关闭所有客户端"""
        for client in self._clients.values():
            client.stop()
        self._clients.clear()


# 全局服务实例
_service: LspToolsService | None = None


def _get_service() -> LspToolsService:
    """获取全局服务实例"""
    global _service
    if _service is None:
        root = os.getenv("ROOTSEEKER_LSP_ROOT") or os.getcwd()
        _service = LspToolsService(default_root=root)
    return _service


def find_symbol_references(
    symbol: str,
    file_path: str | None = None,
    root_path: str | None = None,
) -> list[dict]:
    """
    查找符号引用

    Args:
        symbol: 符号名称
        file_path: 可选，指定文件路径
        root_path: 可选，项目根目录

    Returns:
        引用位置列表
    """
    if not symbol:
        return []

    service = _get_service()

    # 如果提供了文件路径，尝试在该文件中查找符号位置
    if file_path and Path(file_path).exists():
        # 先获取文档符号，找到符号位置
        symbols = service.get_symbols(file_path, root_path)
        for sym in symbols:
            if sym.get("name") == symbol:
                loc = sym.get("location", {})
                line = loc.get("range", {}).get("start", {}).get("line", 0)
                char = loc.get("range", {}).get("start", {}).get("character", 0)
                return service.find_references(file_path, line, char, root_path)

    return []


def go_to_definition(
    file_path: str,
    line: int,
    character: int,
    root_path: str | None = None,
) -> list[dict]:
    """
    跳转到定义

    Args:
        file_path: 文件路径
        line: 行号（0-indexed）
        character: 列号（0-indexed）
        root_path: 可选，项目根目录

    Returns:
        定义位置列表
    """
    service = _get_service()
    return service.go_to_definition(file_path, line, character, root_path)


def get_hover_info(
    file_path: str,
    line: int,
    character: int,
    root_path: str | None = None,
) -> str | None:
    """
    获取悬停信息

    Args:
        file_path: 文件路径
        line: 行号（0-indexed）
        character: 列号（0-indexed）
        root_path: 可选，项目根目录

    Returns:
        悬停信息文本
    """
    service = _get_service()
    return service.get_hover(file_path, line, character, root_path)


def get_document_symbols(
    file_path: str,
    root_path: str | None = None,
) -> list[dict]:
    """
    获取文档符号列表

    Args:
        file_path: 文件路径
        root_path: 可选，项目根目录

    Returns:
        符号列表
    """
    service = _get_service()
    return service.get_symbols(file_path, root_path)
