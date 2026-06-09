from __future__ import annotations

import pytest

from mcp_servers.external import CompositeProductionAdapter
from mcp_servers.internal.adapters import HttpInternalToolAdapter
from rootseeker.config import build_internal_adapter_from_settings
from rootseeker.infra_core import RootSeekerSettings


def test_default_adapter_is_composite() -> None:
    settings = RootSeekerSettings()
    assert settings.internal_adapter_kind == "composite"
    adapter = build_internal_adapter_from_settings(settings)
    assert isinstance(adapter, CompositeProductionAdapter)


def test_build_composite_adapter_explicit() -> None:
    settings = RootSeekerSettings.model_validate({"internal_adapter_kind": "composite"})
    adapter = build_internal_adapter_from_settings(settings)
    assert isinstance(adapter, CompositeProductionAdapter)


def test_legacy_mock_adapter_kind_raises() -> None:
    with pytest.raises(ValueError, match="no longer supported"):
        RootSeekerSettings.model_validate({"internal_adapter_kind": "mock"})


def test_build_http_adapter_from_settings() -> None:
    settings = RootSeekerSettings.model_validate(
        {
            "internal_adapter_kind": "http",
            "internal_http_base_url": "https://example.internal",
            "internal_http_timeout_seconds": 3.5,
        }
    )
    adapter = build_internal_adapter_from_settings(settings)
    assert isinstance(adapter, HttpInternalToolAdapter)
    assert adapter.timeout_seconds == 3.5


def test_build_http_adapter_without_base_url_fails() -> None:
    settings = RootSeekerSettings.model_validate({"internal_adapter_kind": "http"})
    with pytest.raises(ValueError):
        build_internal_adapter_from_settings(settings)


def test_non_prefixed_code_index_env_vars_are_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZOEKT_ENDPOINT", "http://zoekt.local:6070")
    monkeypatch.setenv("QDRANT_ENDPOINT", "http://qdrant.local:6333")
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", "custom_chunks")
    monkeypatch.setenv("ZOEKT_TIMEOUT_SECONDS", "41")
    monkeypatch.setenv("QDRANT_TIMEOUT_SECONDS", "42")

    settings = RootSeekerSettings()

    assert settings.zoekt_endpoint == "http://zoekt.local:6070"
    assert settings.qdrant_endpoint == "http://qdrant.local:6333"
    assert settings.qdrant_collection_name == "custom_chunks"
    assert settings.zoekt_timeout_seconds == 41
    assert settings.qdrant_timeout_seconds == 42
