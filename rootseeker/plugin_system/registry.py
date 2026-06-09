from __future__ import annotations

from rootseeker.contracts.plugin import PluginManifest
from rootseeker.plugin_system.capability import RegisteredCapability

__all__ = ["ManifestRegistry"]


class ManifestRegistry:
    """In-memory registry: plugin manifests + capability -> plugin index."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._capability_index: dict[str, RegisteredCapability] = {}

    def register(self, manifest: PluginManifest) -> None:
        if manifest.plugin_id in self._plugins:
            raise ValueError(f"Duplicate plugin_id: {manifest.plugin_id}")
        self._plugins[manifest.plugin_id] = manifest
        for cap in manifest.capabilities:
            self._index_capability(cap, manifest, is_mcp_tool=False)
        for tool in manifest.mcp_tools:
            self._index_capability(tool, manifest, is_mcp_tool=True)

    def _index_capability(
        self,
        capability_id: str,
        manifest: PluginManifest,
        *,
        is_mcp_tool: bool,
    ) -> None:
        if capability_id in self._capability_index:
            raise ValueError(
                f"Capability or tool '{capability_id}' already registered by "
                f"{self._capability_index[capability_id].plugin_id}"
            )
        self._capability_index[capability_id] = RegisteredCapability(
            capability_id=capability_id,
            plugin_id=manifest.plugin_id,
            kind=manifest.kind,
            is_mcp_tool=is_mcp_tool,
        )

    def get_plugin(self, plugin_id: str) -> PluginManifest | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[PluginManifest]:
        return list(self._plugins.values())

    def resolve_capability(self, capability_id: str) -> RegisteredCapability | None:
        return self._capability_index.get(capability_id)

    def list_capabilities(self) -> list[RegisteredCapability]:
        return list(self._capability_index.values())
