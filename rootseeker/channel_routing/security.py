from __future__ import annotations

import hmac
from hashlib import sha256

from rootseeker.channel_routing.models import ChannelMessage

__all__ = ["ChannelSecurity"]


class ChannelSecurity:
    def __init__(self, *, allowlist_ips: set[str] | None = None, signing_secret: str | None = None) -> None:
        self._allowlist_ips = allowlist_ips or set()
        self._signing_secret = signing_secret

    def validate(self, message: ChannelMessage) -> None:
        if self._allowlist_ips and message.remote_ip not in self._allowlist_ips:
            raise ValueError("source ip is not allowed")
        if self._signing_secret:
            supplied = message.headers.get("x-signature", "")
            expected = hmac.new(
                self._signing_secret.encode("utf-8"),
                str(sorted(message.payload.items())).encode("utf-8"),
                sha256,
            ).hexdigest()
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("invalid signature")
