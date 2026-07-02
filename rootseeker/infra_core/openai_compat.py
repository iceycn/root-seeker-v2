from __future__ import annotations

import time
from typing import Any

import httpx

MIMO_PLATFORM_URL = "https://platform.xiaomimimo.com/"
MIMO_PAYG_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_TOKEN_PLAN_CN_OPENAI_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_TOKEN_PLAN_CN_ANTHROPIC_BASE_URL = "https://token-plan-cn.xiaomimimo.com/anthropic"

_LEGACY_MIMO_BASE_URLS = frozenset(
    {
        "https://api.mimo.mi.com/v1",
        "http://api.mimo.mi.com/v1",
        "https://platform.mimo.mi.com",
        "https://platform.mimo.mi.com/",
    }
)

__all__ = [
    "MIMO_PAYG_BASE_URL",
    "MIMO_PLATFORM_URL",
    "MIMO_TOKEN_PLAN_CN_ANTHROPIC_BASE_URL",
    "MIMO_TOKEN_PLAN_CN_OPENAI_BASE_URL",
    "build_openai_compat_headers",
    "is_mimo_token_plan_key",
    "resolve_mimo_base_url",
    "test_openai_compatible_connection",
]


def is_mimo_token_plan_key(api_key: str) -> bool:
    return (api_key or "").strip().startswith("tp-")


def build_openai_compat_headers(api_key: str, *, include_json: bool = True) -> dict[str, str]:
    headers: dict[str, str] = {}
    if include_json:
        headers["Content-Type"] = "application/json"
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["api-key"] = key
    return headers


def _normalized(url: str) -> str:
    return (url or "").strip().rstrip("/")


def resolve_mimo_base_url(
    *,
    api_key: str,
    base_url: str = "",
    provider_type: str = "openai_compatible",
) -> str:
    key = (api_key or "").strip()
    url = _normalized(base_url)

    if provider_type == "anthropic_compatible":
        if is_mimo_token_plan_key(key) or not url or url in _LEGACY_MIMO_BASE_URLS or url == _normalized(
            MIMO_PAYG_BASE_URL
        ):
            return MIMO_TOKEN_PLAN_CN_ANTHROPIC_BASE_URL
        return url

    if is_mimo_token_plan_key(key):
        if not url or url in _LEGACY_MIMO_BASE_URLS or url == _normalized(MIMO_PAYG_BASE_URL):
            return MIMO_TOKEN_PLAN_CN_OPENAI_BASE_URL
        return url

    if url in _LEGACY_MIMO_BASE_URLS:
        return MIMO_PAYG_BASE_URL
    return url or MIMO_PAYG_BASE_URL


def test_openai_compatible_connection(
    *,
    base_url: str,
    api_key: str = "",
    model: str = "",
    name: str = "",
    display_name: str = "",
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    endpoint = _normalized(base_url)
    if not endpoint:
        return {"ok": False, "name": name, "error": "base_url is empty"}

    get_headers = build_openai_compat_headers(api_key, include_json=False)
    post_headers = build_openai_compat_headers(api_key)
    label = display_name or name or endpoint

    try:
        started = time.perf_counter()
        with httpx.Client(timeout=timeout_seconds, trust_env=False) as client:
            response = client.get(f"{endpoint}/models", headers=get_headers)
            if response.status_code in {404, 405}:
                probe_model = (model or "mimo-v2.5-pro").strip()
                response = client.post(
                    f"{endpoint}/chat/completions",
                    headers=post_headers,
                    json={
                        "model": probe_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_completion_tokens": 8,
                    },
                )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            ok = 200 <= response.status_code < 300
            result: dict[str, Any] = {
                "ok": ok,
                "name": name,
                "display_name": label,
                "response_ms": elapsed_ms,
                "status_code": response.status_code,
                "body_preview": response.text[:500],
            }
            if not ok:
                result["error"] = response.text[:300]
            return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "name": name, "display_name": label, "error": str(exc)}
