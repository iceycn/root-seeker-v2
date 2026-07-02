from __future__ import annotations

import os
import time

import httpx

__all__ = ["get_with_retry", "outbound_http_client", "resolve_http_proxy"]


def resolve_http_proxy() -> str | None:
    for key in (
        "ROOTSEEKER_HTTP_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "https_proxy",
        "http_proxy",
    ):
        value = (os.getenv(key) or "").strip()
        if value:
            # Docker 容器内访问宿主机代理时，127.0.0.1 需要替换为 host.docker.internal
            if "127.0.0.1" in value:
                value = value.replace("127.0.0.1", "host.docker.internal")
            return value
    return None


def outbound_http_client(**kwargs: object) -> httpx.Client:
    proxy = resolve_http_proxy()
    timeout = kwargs.pop("timeout", 30.0)
    client_kwargs: dict[str, object] = {
        "timeout": timeout,
        "trust_env": proxy is None,
    }
    if proxy:
        client_kwargs["proxy"] = proxy
    client_kwargs.update(kwargs)
    return httpx.Client(**client_kwargs)


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    retries: int = 3,
    retry_delay_seconds: float = 0.6,
    **kwargs: object,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return client.get(url, **kwargs)
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(retry_delay_seconds * (attempt + 1))
    assert last_error is not None
    raise last_error
