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

    def test_transform_search_response_caps_line_hits(self) -> None:
        adapter = ZoektCodeAdapter(config=ZoektConfig())
        files = []
        for i in range(10):
            files.append(
                {
                    "Repository": "demo",
                    "FileName": f"f{i}.java",
                    "LineMatches": [
                        {"LineNumber": j, "Line": f"line {j}", "Score": 1.0}
                        for j in range(20)
                    ],
                }
            )
        result = adapter._transform_search_response(
            "q",
            {"Result": {"Files": files}},
            max_hits=50,
        )
        assert len(result["hits"]) == 50
        assert result["truncated"] is True
        assert result["total"] == 200
        scores = [float(h["score"]) for h in result["hits"]]
        assert scores == sorted(scores, reverse=True)

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

    def test_read_file_uses_fuzzy_repo_and_package_path(self, tmp_path, monkeypatch) -> None:
        from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

        repo_root = tmp_path / "6183d17ff1ae9b61971d96b5__coolcollege__backend__user-center-api"
        rel = (
            "user-center-facade/src/main/java/net/coolcollege/usercenter/facade/handler/"
            "AesTypeHandler.java"
        )
        java = repo_root / rel
        java.parent.mkdir(parents=True)
        java.write_text("public class AesTypeHandler {}\n", encoding="utf-8")
        monkeypatch.setenv("ROOTSEEKER_REPO_BASE_PATH", str(tmp_path))

        adapter = ZoektCodeAdapter(config=ZoektConfig(endpoint="http://zoekt.test"))
        adapter._client = _zoekt_client_without_api_file(
            [
                ("6183d17ff1ae9b61971d96b5__training-manage-api", "/repos/6183d17ff1ae9b61971d96b5__training-manage-api"),
                (
                    "6183d17ff1ae9b61971d96b5__coolcollege__backend__user-center-api",
                    "/repos/6183d17ff1ae9b61971d96b5__coolcollege__backend__user-center-api",
                ),
            ]
        )

        result = adapter.read_file(
            "net/coolcollege/usercenter/facade/handler/AesTypeHandler.java",
            repo="training-manage-api",
        )
        assert "public class AesTypeHandler" in result["content"]
        assert "error" not in result

    def test_read_file_search_fallback_when_local_path_missing(self, tmp_path, monkeypatch) -> None:
        from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

        repo_root = tmp_path / "6183__user-center-api"
        rel = "user-center-facade/src/main/java/net/coolcollege/usercenter/facade/handler/AesTypeHandler.java"
        java = repo_root / rel
        java.parent.mkdir(parents=True)
        java.write_text("class AesTypeHandler { int line; }\n", encoding="utf-8")
        monkeypatch.setenv("ROOTSEEKER_REPO_BASE_PATH", str(tmp_path))

        adapter = ZoektCodeAdapter(config=ZoektConfig(endpoint="http://zoekt.test"))
        adapter._client = _zoekt_client_without_api_file(
            [("6183__user-center-api", "/repos/missing-on-host/6183__user-center-api")],
            search_hits=[
                {
                    "Repository": "6183__user-center-api",
                    "FileName": rel,
                    "LineMatches": [{"LineNumber": 1, "Line": "class AesTypeHandler", "Score": 10.0}],
                }
            ],
        )

        result = adapter.read_file(
            "net/coolcollege/usercenter/facade/handler/AesTypeHandler.java",
            repo="user-center-api",
        )
        assert "class AesTypeHandler" in result["content"]
        assert result["path"] == rel

    def test_read_file_does_not_pick_same_filename_in_other_repo(
        self, tmp_path, monkeypatch
    ) -> None:
        from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

        user_rel = (
            "user-center-service/src/main/java/net/coolcollege/usercenter/"
            "service/business/impl/SysUserGroupService.java"
        )
        eval_rel = "src/main/java/net/coolcollege/evaluation/api/service/SysUserGroupService.java"
        user_root = tmp_path / "6183__user-center-api"
        eval_root = tmp_path / "6183__evaluation-api"
        user_java = user_root / user_rel
        eval_java = eval_root / eval_rel
        user_java.parent.mkdir(parents=True)
        eval_java.parent.mkdir(parents=True)
        user_java.write_text("class SysUserGroupService { void parseFile() {} }\n", encoding="utf-8")
        eval_java.write_text("class SysUserGroupService { /* evaluation stub */ }\n", encoding="utf-8")
        monkeypatch.setenv("ROOTSEEKER_REPO_BASE_PATH", str(tmp_path))

        adapter = ZoektCodeAdapter(config=ZoektConfig(endpoint="http://zoekt.test"))
        adapter._client = _zoekt_client_without_api_file(
            [
                ("6183__evaluation-api", str(eval_root)),
                ("6183__user-center-api", str(user_root)),
            ],
            search_hits=[
                {
                    "Repository": "6183__evaluation-api",
                    "FileName": eval_rel,
                    "LineMatches": [{"LineNumber": 1, "Line": "class SysUserGroupService", "Score": 20.0}],
                },
                {
                    "Repository": "6183__user-center-api",
                    "FileName": user_rel,
                    "LineMatches": [{"LineNumber": 1, "Line": "void parseFile()", "Score": 5.0}],
                },
            ],
        )

        result = adapter.read_file(
            "usercenter/src/main/java/net/coolcollege/usercenter/service/business/impl/"
            "SysUserGroupService.java",
            repo="user-center-api",
        )
        assert "parseFile" in result["content"]
        assert "evaluation stub" not in result["content"]
        assert result["path"] == user_rel
        assert str(result.get("repo") or "").endswith("user-center-api")

    def test_read_file_slices_large_java_method_around_focus(self, tmp_path, monkeypatch) -> None:
        from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

        repo_root = tmp_path / "6183__user-center-api"
        rel = "user-center-service/src/main/java/demo/SysUserGroupService.java"
        java = repo_root / rel
        java.parent.mkdir(parents=True)
        body = ["package demo;", "public class SysUserGroupService {"]
        body.extend([f"    int pad{i} = {i};" for i in range(80)])
        body.extend(
            [
                "    public void parseFile() {",
                "        if (empty) {",
                '            throw new ServiceException("enterpriseapi.550008");',
                "        }",
                "    }",
                "}",
            ]
        )
        java.write_text("\n".join(body) + "\n", encoding="utf-8")
        monkeypatch.setenv("ROOTSEEKER_REPO_BASE_PATH", str(tmp_path))
        adapter = ZoektCodeAdapter(config=ZoektConfig(endpoint="http://zoekt.test"))
        adapter._client = _zoekt_client_without_api_file(
            [("6183__user-center-api", str(repo_root))]
        )
        result = adapter.read_file(
            rel, repo="user-center-api", focus_line=84, methods=["parseFile"]
        )
        assert "550008" in result["content"]
        assert "parseFile" in result["content"]
        assert result["returned_lines"] < result["total_lines"]
        assert result["returned_lines"] < 40
        assert "pad0" not in result["content"]

    def test_read_file_keeps_only_call_chain_methods(self, tmp_path, monkeypatch) -> None:
        from mcp_servers.external.zoekt_adapter import ZoektCodeAdapter, ZoektConfig

        repo_root = tmp_path / "6183__user-center-facade"
        rel = "src/main/java/net/coolcollege/usercenter/facade/handler/AesTypeHandler.java"
        java = repo_root / rel
        java.parent.mkdir(parents=True)
        java.write_text(
            "\n".join(
                [
                    "package net.coolcollege.usercenter.facade.handler;",
                    "public class AesTypeHandler extends BaseTypeHandler<String> {",
                    "    public String getNullableResult(ResultSet rs, String columnName) {",
                    "        return decryptField(rs.getString(columnName));",
                    "    }",
                    "    public String unusedHelper() {",
                    '        return "nope";',
                    "    }",
                    "    private String decryptField(String encrypted) {",
                    "        return AesEncryptUtil.decrypt(encrypted);",
                    "    }",
                    "}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("ROOTSEEKER_REPO_BASE_PATH", str(tmp_path))
        adapter = ZoektCodeAdapter(config=ZoektConfig(endpoint="http://zoekt.test"))
        adapter._client = _zoekt_client_without_api_file(
            [("6183__user-center-facade", str(repo_root))]
        )
        result = adapter.read_file(
            rel,
            repo="user-center-facade",
            methods=["getNullableResult", "decryptField"],
        )
        assert "getNullableResult" in result["content"]
        assert "decryptField" in result["content"]
        assert "AesEncryptUtil.decrypt" in result["content"]
        assert "unusedHelper" not in result["content"]
        assert "nope" not in result["content"]


def _zoekt_client_without_api_file(
    repos: list[tuple[str, str]],
    search_hits: list[dict] | None = None,
) -> MagicMock:
    list_payload = {
        "List": {
            "Repos": [
                {
                    "Repository": {"Name": name, "Source": source, "URL": "", "Branches": []},
                    "IndexMetadata": {"IndexTime": ""},
                }
                for name, source in repos
            ]
        }
    }
    list_response = MagicMock()
    list_response.status_code = 200
    list_response.raise_for_status = MagicMock()
    list_response.json.return_value = list_payload

    search_response = MagicMock()
    search_response.status_code = 200
    search_response.raise_for_status = MagicMock()
    search_response.json.return_value = {"Result": {"Files": search_hits or []}}

    file_response = MagicMock()
    file_response.status_code = 404

    client = MagicMock()

    def get(url, params=None):
        if str(url).endswith("/api/file"):
            return file_response
        raise AssertionError(f"unexpected GET {url}")

    def post(url, json=None):
        if str(url).endswith("/api/list"):
            return list_response
        if str(url).endswith("/api/search"):
            return search_response
        raise AssertionError(f"unexpected POST {url}")

    client.get.side_effect = get
    client.post.side_effect = post
    return client
