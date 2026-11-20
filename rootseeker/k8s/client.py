"""Minimal Kubernetes API client used by the anomaly-analysis reader."""

from __future__ import annotations

from typing import Any

import httpx

from rootseeker.k8s.config import K8sConfig

__all__ = ["KubernetesApiClient", "KubernetesApiError"]


class KubernetesApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KubernetesApiClient:
    def __init__(
        self,
        config: K8sConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if config.verify_ssl and config.ca_cert:
            verify: bool | str = config.ca_cert
        else:
            verify = config.verify_ssl
        self._http = httpx.Client(
            base_url=config.api_server.rstrip("/"),
            headers={"Authorization": f"Bearer {config.token}"},
            verify=verify,
            timeout=config.timeout_seconds,
            trust_env=False,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = self._request(path, params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise KubernetesApiError("Kubernetes API 返回的不是 JSON") from exc
        if not isinstance(payload, dict):
            raise KubernetesApiError("Kubernetes API 返回的不是 JSON 对象")
        return payload

    def get_text(self, path: str, params: dict[str, str] | None = None) -> str:
        return self._request(path, params).text

    def _request(self, path: str, params: dict[str, str] | None) -> httpx.Response:
        try:
            response = self._http.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise KubernetesApiError(str(exc)) from exc
        if response.status_code >= 400:
            raise KubernetesApiError(_error_detail(response), response.status_code)
        return response


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()[:500]
    text = response.text.strip()
    if text:
        return text[:500]
    return f"Kubernetes API HTTP {response.status_code}"
