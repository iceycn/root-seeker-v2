from pathlib import Path

from rootseeker.plugin_system import build_registry_from_bundled


def _repo_root() -> Path:
    # tests/unit/plugin_system/test_*.py -> repo root is four levels up
    return Path(__file__).resolve().parents[3]


def test_discover_and_register_all_bundled_plugins() -> None:
    root = _repo_root()
    builtin = root / "plugins" / "builtin"
    registry = build_registry_from_bundled(builtin)
    plugins = {p.plugin_id for p in registry.list_plugins()}
    assert "builtin.service_catalog" in plugins
    assert "builtin.log_query" in plugins
    assert "builtin.code_index" in plugins
    assert "builtin.notify" in plugins
    assert "builtin.default_log_triage_flow" in plugins


def test_resolve_mcp_tools() -> None:
    root = _repo_root()
    registry = build_registry_from_bundled(root / "plugins" / "builtin")
    rc = registry.resolve_capability("catalog.resolve_service")
    assert rc is not None
    assert rc.plugin_id == "builtin.service_catalog"
    assert rc.is_mcp_tool is True
    trace = registry.resolve_capability("trace.get_chain")
    assert trace is not None
    assert trace.plugin_id == "builtin.log_query"


def test_resolve_logical_capability() -> None:
    root = _repo_root()
    registry = build_registry_from_bundled(root / "plugins" / "builtin")
    flow = registry.resolve_capability("flow.builtin.default_log_triage")
    assert flow is not None
    assert flow.plugin_id == "builtin.default_log_triage_flow"
    assert flow.is_mcp_tool is False
    plugin = registry.get_plugin("builtin.default_log_triage_flow")
    assert plugin is not None
    assert plugin.mcp_tools == []
