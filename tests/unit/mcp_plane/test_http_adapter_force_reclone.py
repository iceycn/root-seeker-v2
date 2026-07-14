from __future__ import annotations

import httpx

from mcp_servers.internal.adapters import HttpInternalToolAdapter


def test_http_adapter_repo_sync_forwards_force_reclone() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Response(200).json if False else None
        import json

        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ok": True, "repo_name": "demo", "state": "completed", "message": "ok"})

    transport = httpx.MockTransport(handler)
    adapter = HttpInternalToolAdapter(base_url="http://internal.test", transport=transport)
    result = adapter.repo_sync({"name": "demo", "trigger_index": True, "force_reclone": True})

    assert result["ok"] is True
    assert captured["url"] == "http://internal.test/repos/demo/sync"
    assert captured["payload"] == {"trigger_index": True, "force_reclone": True}


def test_http_adapter_find_callers_uses_configured_route() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"target": None, "static_callers": []})

    transport = httpx.MockTransport(handler)
    adapter = HttpInternalToolAdapter(base_url="http://internal.test", transport=transport)
    result = adapter.find_callers({"call_chain": ["Foo.bar (Foo.java:1)"]})

    assert result["static_callers"] == []
    assert captured["url"] == "http://internal.test/code/find_callers"
    assert captured["payload"]["call_chain"] == ["Foo.bar (Foo.java:1)"]


def test_http_adapter_find_callers_uses_extended_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"target": None, "static_callers": []})

    original_client = httpx.Client

    def client_factory(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)

    transport = httpx.MockTransport(handler)
    adapter = HttpInternalToolAdapter(
        base_url="http://internal.test",
        transport=transport,
        timeout_seconds=5.0,
        find_callers_timeout_seconds=120.0,
    )
    adapter.find_callers({"call_chain": ["Foo.bar (Foo.java:1)"]})

    assert captured["timeout"] == 120.0
