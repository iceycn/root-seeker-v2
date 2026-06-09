from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

__all__ = ["NetworkGuard"]


class NetworkGuard:
    def __init__(self, *, timeout_seconds: float = 5.0, allow_private: bool = False) -> None:
        self.timeout_seconds = timeout_seconds
        self.allow_private = allow_private

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https are allowed")
        if not parsed.hostname:
            raise ValueError("hostname is required")
        self._validate_host(parsed.hostname)

    def _validate_host(self, host: str) -> None:
        try:
            ip = ip_address(host)
        except ValueError:
            return
        if not self.allow_private and (ip.is_private or ip.is_loopback or ip.is_link_local):
            raise ValueError(f"private/loopback address is blocked: {host}")
