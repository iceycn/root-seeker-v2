from __future__ import annotations

from pathlib import Path

from rootseeker.contracts.plugin import PluginManifest
from rootseeker.plugin_system.discovery import discover_bundled_plugin_manifests
from rootseeker.plugin_system.manifest import load_manifest_from_path
from rootseeker.plugin_system.registry import ManifestRegistry

__all__ = ["build_registry_from_bundled", "register_manifest"]


def register_manifest(registry: ManifestRegistry, manifest: PluginManifest) -> None:
    registry.register(manifest)


def build_registry_from_bundled(builtin_root: Path) -> ManifestRegistry:
    registry = ManifestRegistry()
    for manifest_path in discover_bundled_plugin_manifests(builtin_root):
        register_manifest(registry, load_manifest_from_path(manifest_path))
    return registry
