"""Verify API exposes every route expected by HttpInternalToolAdapter."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app

_EXPECTED_ROUTES: list[tuple[str, str, dict]] = [
    ("POST", "/catalog/resolve_service", {"tenant": "demo", "environment": "prod", "service_name": "order-service"}),
    ("POST", "/catalog/get_log_sources", {"tenant": "demo", "environment": "prod", "service_name": "order-service"}),
    ("POST", "/log/query_by_trace_id", {"trace_id": "trace-1", "service_name": "order-service"}),
    ("POST", "/log/query_by_template", {"template_id": "error-template"}),
    ("POST", "/trace/get_chain", {"trace_id": "trace-1"}),
    ("POST", "/code/search", {"query": "OrderService"}),
    ("POST", "/code/read", {"path": "README.md"}),
    ("POST", "/index/get_status", {}),
    ("POST", "/notify/send", {"channel": "webhook", "message": "test"}),
    ("POST", "/lsp/references", {"symbol": "main"}),
    ("POST", "/lsp/definition", {"file_path": "README.md", "line": 1, "character": 0}),
    ("POST", "/lsp/hover", {"file_path": "README.md", "line": 1, "character": 0}),
    ("POST", "/lsp/symbols", {"file_path": "README.md"}),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_api_internal_http_bridge_routes_are_registered() -> None:
    client = TestClient(create_app(_repo_root()))

    for method, path, body in _EXPECTED_ROUTES:
        if method == "POST":
            response = client.post(path, json=body)
        else:
            response = client.request(method, path, json=body)
        assert response.status_code != 404, f"{method} {path} returned 404"


def test_catalog_resolve_service_returns_entry_shape() -> None:
    client = TestClient(create_app(_repo_root()))
    response = client.post(
        "/catalog/resolve_service",
        json={"tenant": "demo", "environment": "prod", "service_name": "order-service"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "entry" in payload
    assert payload["entry"]["service_name"] == "order-service"
