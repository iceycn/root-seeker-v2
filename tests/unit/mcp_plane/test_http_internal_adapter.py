from __future__ import annotations

import json

import httpx

from mcp_servers.internal.adapters import HttpInternalToolAdapter


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        path = request.url.path
        if path == "/catalog/resolve_service":
            return httpx.Response(
                200,
                json={
                    "entry": {
                        "tenant": payload.get("tenant", "demo"),
                        "environment": payload.get("environment", "prod"),
                        "service_name": payload.get("service_name", "unknown"),
                        "display_name": "HTTP Service",
                        "log_sources": [{"source_id": "http-log", "type": "http"}],
                        "repositories": [],
                        "trace_sources": [],
                        "metadata": {},
                    }
                },
            )
        if path == "/catalog/get_log_sources":
            return httpx.Response(200, json={"sources": [{"source_id": "http-log", "type": "http"}]})
        if path == "/log/query_by_trace_id":
            return httpx.Response(200, json={"query_key": "trace:t1", "records": [], "truncated": False})
        if path == "/notify/send":
            return httpx.Response(200, json={"channel": "http", "status": "sent"})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


def test_http_adapter_resolve_service() -> None:
    adapter = HttpInternalToolAdapter(base_url="https://example.internal", transport=_transport())
    entry = adapter.resolve_service("demo", "prod", "order-service")
    assert entry.display_name == "HTTP Service"


def test_http_adapter_log_sources_and_notify() -> None:
    adapter = HttpInternalToolAdapter(base_url="https://example.internal", transport=_transport())
    sources = adapter.get_log_sources("demo", "prod", "order-service")
    assert sources and sources[0]["source_id"] == "http-log"

    sent = adapter.send_notification("http", "hello")
    assert sent == {"channel": "http", "status": "sent"}
