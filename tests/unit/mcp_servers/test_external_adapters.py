"""Tests for external production adapters."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from mcp_servers.external import (
    JaegerConfig,
    JaegerTraceAdapter,
    SlsConfig,
    SlsLogAdapter,
    ZoektCodeAdapter,
    ZoektConfig,
)


class TestSlsLogAdapter:
    """Tests for SLS log adapter."""

    def test_config_from_env(self) -> None:
        """Test config loading from environment."""
        with patch.dict(
            "os.environ",
            {
                "SLS_ACCESS_KEY_ID": "test-key",
                "SLS_ACCESS_KEY_SECRET": "test-secret",
                "SLS_ENDPOINT": "cn-hangzhou.log.aliyuncs.com",
                "SLS_PROJECT": "test-project",
                "SLS_LOGSTORE": "test-logstore",
            },
        ):
            config = SlsConfig.from_env()
            assert config.access_key_id == "test-key"
            assert config.access_key_secret == "test-secret"
            assert config.endpoint == "cn-hangzhou.log.aliyuncs.com"
            assert config.project == "test-project"
            assert config.logstore == "test-logstore"
            assert config.is_configured()

    def test_config_not_configured(self) -> None:
        """Test config check when missing fields."""
        config = SlsConfig()
        assert not config.is_configured()

    def test_no_client_when_not_configured(self) -> None:
        """Explicit error payload when SLS is not configured (no fabricated log lines)."""
        adapter = SlsLogAdapter(config=SlsConfig())
        result = adapter.query_logs_by_trace_id("trace-123")

        md = result.get("metadata", {})
        assert md.get("configured") is False
        assert md.get("error")
        assert result.get("records") == []

    def test_query_logs_by_template_unconfigured(self) -> None:
        """Template query surfaces unconfigured state."""
        adapter = SlsLogAdapter(config=SlsConfig())
        result = adapter.query_logs_by_template("tpl-error-500")

        md = result.get("metadata", {})
        assert md.get("configured") is False
        assert md.get("error")

    def test_custom_query_unconfigured(self) -> None:
        adapter = SlsLogAdapter(config=SlsConfig())
        result = adapter.query_logs('level:ERROR AND service:"order-service"')

        md = result.get("metadata", {})
        assert md.get("configured") is False
        assert md.get("error")

    def test_sls_records_are_normalized_for_log_query_contract(self) -> None:
        adapter = SlsLogAdapter(config=SlsConfig())
        records = adapter._normalize_records(  # noqa: SLF001
            [
                {
                    "__time__": 1_700_000_000,
                    "msg": "database timeout",
                    "severity": "ERROR",
                    "traceId": "trace-1",
                    "custom": "value",
                }
            ]
        )

        assert records[0]["message"] == "database timeout"
        assert records[0]["level"] == "ERROR"
        assert records[0]["trace_id"] == "trace-1"
        assert records[0]["raw"]["custom"] == "value"


class TestJaegerTraceAdapter:
    """Tests for Jaeger trace adapter."""

    def test_config_from_env(self) -> None:
        """Test config loading from environment."""
        with patch.dict(
            "os.environ",
            {
                "JAEGER_ENDPOINT": "http://jaeger:16686",
                "JAEGER_TIMEOUT_SECONDS": "15.0",
            },
        ):
            config = JaegerConfig.from_env()
            assert config.endpoint == "http://jaeger:16686"
            assert config.timeout_seconds == 15.0
            assert config.is_configured()

    def test_trace_chain_when_jaeger_unconfigured(self) -> None:
        adapter = JaegerTraceAdapter(config=JaegerConfig())
        result = adapter.get_trace_chain("trace-abc123")

        assert result.get("configured") is False
        assert result["trace_id"] == "trace-abc123"
        assert result["spans"] == []

    def test_search_traces_when_jaeger_unconfigured(self) -> None:
        adapter = JaegerTraceAdapter(config=JaegerConfig())
        result = adapter.search_traces("order-service", operation="HTTP GET")

        assert result.get("configured") is False
        assert result["traces"] == []


class TestZoetCodeAdapter:
    """Tests for Zoekt code adapter."""

    def test_config_from_env(self) -> None:
        """Test config loading from environment."""
        with patch.dict(
            "os.environ",
            {
                "ZOEKT_ENDPOINT": "http://zoekt:6070",
                "ZOEKT_TIMEOUT_SECONDS": "20.0",
            },
        ):
            config = ZoektConfig.from_env()
            assert config.endpoint == "http://zoekt:6070"
            assert config.timeout_seconds == 20.0
            assert config.is_configured()

    def test_config_from_env_rootseeker_endpoint_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ZOEKT_ENDPOINT": "",
                "ROOTSEEKER_ZOEKT_ENDPOINT": "http://fallback-z:6070",
                "ZOEKT_TIMEOUT_SECONDS": "",
                "ROOTSEEKER_ZOEKT_TIMEOUT_SECONDS": "12",
            },
            clear=False,
        ):
            cfg = ZoektConfig.from_env()
            assert cfg.endpoint == "http://fallback-z:6070"
            assert cfg.timeout_seconds == 12.0
            assert cfg.is_configured()

    def test_search_when_zoekt_unconfigured(self) -> None:
        adapter = ZoektCodeAdapter(config=ZoektConfig())
        result = adapter.search_code("function handleError")

        assert result.get("configured") is False
        assert result["hits"] == []
        assert "error" in result

    def test_read_file_unconfigured(self) -> None:
        adapter = ZoektCodeAdapter(config=ZoektConfig())
        result = adapter.read_file("src/handlers/error.py")

        assert result.get("configured") is False
        assert result["path"] == "src/handlers/error.py"

    def test_index_status_unconfigured(self) -> None:
        adapter = ZoektCodeAdapter(config=ZoektConfig())
        result = adapter.get_index_status()

        assert result.get("configured") is False
        assert result["ready"] is False
        assert result["indexes"] == []


class TestAdapterWithMockedHttp:
    """Tests with mocked HTTP responses."""

    def test_jaeger_real_response(self) -> None:
        """Test Jaeger with mocked HTTP response."""
        config = JaegerConfig(endpoint="http://jaeger:16686")
        adapter = JaegerTraceAdapter(config=config)

        # Mock the _client directly
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "traceID": "trace-123",
                    "spans": [
                        {
                            "spanID": "span-1",
                            "parentSpanID": "",
                            "operationName": "HTTP GET /api",
                            "process": {"serviceName": "api-gateway"},
                            "startTime": 1000000,
                            "duration": 500000,
                            "tags": [],
                            "logs": [],
                        },
                    ],
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        adapter._client = mock_client

        result = adapter.get_trace_chain("trace-123")

        assert result.get("error") is None
        assert len(result["spans"]) == 1
        assert result["spans"][0]["operation_name"] == "HTTP GET /api"

    def test_zoekt_real_search(self) -> None:
        """Test Zoekt with mocked HTTP response."""
        config = ZoektConfig(endpoint="http://zoekt:6070")
        adapter = ZoektCodeAdapter(config=config)

        # Mock the _client directly
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Result": [
                {
                    "Repository": "test-repo",
                    "FileMatches": [
                        {
                            "FileName": "src/main.py",
                            "LineMatches": [
                                {
                                    "LineNumber": 42,
                                    "Line": "def main():",
                                    "Score": 1.0,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        adapter._client = mock_client

        result = adapter.search_code("def main")

        assert result.get("error") is None
        assert len(result["hits"]) == 1
        assert result["hits"][0]["path"] == "src/main.py"
        mock_client.post.assert_called()
