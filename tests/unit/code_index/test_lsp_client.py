from __future__ import annotations

from rootseeker.code_index import (
    LspClient,
    LspClientConfig,
    LspLocation,
    LspPosition,
    LspRange,
    LspServerType,
    LspSymbolInfo,
    LspToolsService,
)


def test_lsp_position() -> None:
    """测试 LSP 位置"""
    pos = LspPosition(line=10, character=5)
    assert pos.line == 10
    assert pos.character == 5
    assert pos.to_dict() == {"line": 10, "character": 5}


def test_lsp_range() -> None:
    """测试 LSP 范围"""
    start = LspPosition(line=0, character=0)
    end = LspPosition(line=10, character=20)
    range_obj = LspRange(start=start, end=end)

    assert range_obj.start.line == 0
    assert range_obj.end.line == 10
    assert range_obj.to_dict() == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 10, "character": 20},
    }


def test_lsp_location() -> None:
    """测试 LSP 位置（文件+范围）"""
    loc = LspLocation(
        uri="file:///test.py",
        range=LspRange(
            start=LspPosition(line=0, character=0),
            end=LspPosition(line=5, character=10),
        ),
    )

    assert loc.uri == "file:///test.py"
    assert loc.range.start.line == 0


def test_lsp_symbol_info() -> None:
    """测试符号信息"""
    symbol = LspSymbolInfo(
        name="TestClass",
        kind=5,  # Class
        location=LspLocation(
            uri="file:///test.py",
            range=LspRange(
                start=LspPosition(line=0, character=0),
                end=LspPosition(line=10, character=0),
            ),
        ),
        container_name="test_module",
    )

    assert symbol.name == "TestClass"
    assert symbol.kind == 5
    assert symbol.container_name == "test_module"

    data = symbol.to_dict()
    assert data["name"] == "TestClass"
    assert data["kind"] == 5


def test_lsp_client_config() -> None:
    """测试 LSP 客户端配置"""
    config = LspClientConfig(server_type=LspServerType.PYRIGHT)

    assert config.server_type == LspServerType.PYRIGHT
    cmd = config.get_server_command()
    assert "pyright-langserver" in cmd[0]


def test_lsp_client_config_custom_command() -> None:
    """测试自定义命令"""
    config = LspClientConfig(server_command=["my-lsp", "--stdio"])

    cmd = config.get_server_command()
    assert cmd == ["my-lsp", "--stdio"]


def test_lsp_client_detect_language() -> None:
    """测试语言检测"""
    client = LspClient()

    assert client._detect_language("test.py") == "python"
    assert client._detect_language("test.js") == "javascript"
    assert client._detect_language("test.ts") == "typescript"
    assert client._detect_language("test.go") == "go"
    assert client._detect_language("test.rs") == "rust"
    assert client._detect_language("test.java") == "java"
    assert client._detect_language("test.unknown") == "plaintext"


def test_lsp_client_parse_location() -> None:
    """测试位置解析"""
    client = LspClient()

    item = {
        "uri": "file:///test.py",
        "range": {
            "start": {"line": 5, "character": 0},
            "end": {"line": 10, "character": 20},
        },
    }

    loc = client._parse_location(item)
    assert loc is not None
    assert loc.uri == "file:///test.py"
    assert loc.range.start.line == 5
    assert loc.range.end.line == 10


def test_lsp_tools_service_detect_root() -> None:
    """测试根目录检测"""
    service = LspToolsService()

    # 测试不存在的路径
    root = service._detect_root("/nonexistent/path/file.py")
    # 应该返回 None 或某个父目录
    assert root is None or isinstance(root, str)


def test_lsp_tools_service_location_to_dict() -> None:
    """测试位置转换"""
    service = LspToolsService()

    loc = LspLocation(
        uri="file:///test.py",
        range=LspRange(
            start=LspPosition(line=5, character=10),
            end=LspPosition(line=10, character=20),
        ),
    )

    result = service._location_to_dict(loc)

    assert result["uri"] == "file:///test.py"
    assert result["line"] == 5
    assert result["character"] == 10


def test_lsp_client_context_manager() -> None:
    """测试上下文管理器"""
    config = LspClientConfig(server_type=LspServerType.PYRIGHT)

    with LspClient(config) as client:
        assert client is not None
    # 退出后应该已停止


def test_lsp_server_types() -> None:
    """测试服务器类型"""
    assert LspServerType.PYRIGHT.value == "pyright"
    assert LspServerType.PYLSP.value == "pylsp"
    assert LspServerType.GOPALS.value == "gopls"
    assert LspServerType.TYPESCRIPT.value == "typescript-language-server"
    assert LspServerType.RUST_ANALYZER.value == "rust-analyzer"


def test_lsp_client_config_defaults() -> None:
    """测试默认配置"""
    config = LspClientConfig()

    assert config.server_type == LspServerType.PYRIGHT
    assert config.timeout_seconds == 30.0
    assert config.initialization_options == {}


def test_find_symbol_references_empty() -> None:
    """测试空符号查询"""
    from rootseeker.code_index.lsp_tools import find_symbol_references

    result = find_symbol_references("")
    assert result == []


def test_lsp_client_stop() -> None:
    """测试停止客户端"""
    client = LspClient()

    # 停止未启动的客户端应该不报错
    client.stop()
    assert client._process is None
