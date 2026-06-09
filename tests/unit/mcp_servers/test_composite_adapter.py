"""Tests for composite production adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mcp_servers.external import CompositeProductionAdapter, ProductionConfig


class TestCompositeProductionAdapter:
    """Tests for composite production adapter."""

    def test_from_env(self) -> None:
        """Test adapter creation from environment."""
        adapter = CompositeProductionAdapter.from_env()
        assert adapter._sls is not None
        assert adapter._jaeger is not None
        assert adapter._zoekt is not None

    def test_resolve_service_from_catalog(self) -> None:
        """Test service resolution from catalog."""
        adapter = CompositeProductionAdapter.from_env()
        entry = adapter.resolve_service("demo", "prod", "order-service")

        assert entry.tenant == "demo"
        assert entry.environment == "prod"
        assert entry.service_name == "order-service"

    def test_get_log_sources(self) -> None:
        """Test log source retrieval."""
        adapter = CompositeProductionAdapter.from_env()
        sources = adapter.get_log_sources("demo", "prod", "order-service")

        assert isinstance(sources, list)

    def test_query_logs_delegates_to_sls(self) -> None:
        """Test log query delegation to SLS adapter."""
        adapter = CompositeProductionAdapter.from_env()
        result = adapter.query_logs_by_trace_id("trace-123")

        assert "query_key" in result
        assert result.get("metadata", {}).get("configured") is False
        assert result.get("records") == []

    def test_get_trace_chain_delegates_to_jaeger(self) -> None:
        """Test trace chain delegation to Jaeger adapter."""
        adapter = CompositeProductionAdapter.from_env()
        result = adapter.get_trace_chain("trace-abc")

        # Jaeger not configured → empty spans + error field
        assert result["trace_id"] == "trace-abc"
        assert result.get("configured") is False
        assert result["spans"] == []

    def test_search_code_delegates_to_zoekt(self) -> None:
        """Test code search delegation to Zoekt adapter."""
        adapter = CompositeProductionAdapter.from_env()
        result = adapter.search_code("def main")

        # Zoekt not configured → no hits
        assert result.get("configured") is False
        assert result["hits"] == []

    def test_read_code_delegates_to_zoekt(self) -> None:
        """Test file read delegation to Zoekt adapter."""
        adapter = CompositeProductionAdapter.from_env()
        result = adapter.read_code("src/main.py")

        assert result.get("configured") is False
        assert result["path"] == "src/main.py"

    def test_get_index_status_delegates_to_zoekt(self) -> None:
        """Test index status delegation to Zoekt adapter."""
        adapter = CompositeProductionAdapter.from_env()
        result = adapter.get_index_status()

        assert result.get("configured") is False
        assert result["ready"] is False
        assert result["indexes"] == []

    def test_close_closes_all_adapters(self) -> None:
        """Test that close closes all sub-adapters."""
        adapter = CompositeProductionAdapter.from_env()

        # Mock the close methods
        adapter._sls.close = MagicMock()
        adapter._jaeger.close = MagicMock()
        adapter._zoekt.close = MagicMock()

        adapter.close()

        adapter._sls.close.assert_called_once()
        adapter._jaeger.close.assert_called_once()
        adapter._zoekt.close.assert_called_once()


class TestProductionConfig:
    """Tests for production configuration."""

    def test_from_env(self) -> None:
        """Test config loading from environment."""
        with patch.dict(
            "os.environ",
            {
                "SLS_PROJECT": "test-project",
                "JAEGER_ENDPOINT": "http://jaeger:16686",
                "ZOEKT_ENDPOINT": "http://zoekt:6070",
            },
        ):
            config = ProductionConfig.from_env()
            assert config.sls.project == "test-project"
            assert config.jaeger.endpoint == "http://jaeger:16686"
            assert config.zoekt.endpoint == "http://zoekt:6070"

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = ProductionConfig()
        assert config.sls is not None
        assert config.jaeger is not None
        assert config.zoekt is not None
