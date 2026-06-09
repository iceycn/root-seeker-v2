"""Gateway authorization and rate limiting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from rootseeker.contracts.common import utc_now
from rootseeker.gateway.auth import AuthCredentials

__all__ = ["Authorizer", "RateLimiter", "RateLimitResult"]


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    remaining: int
    reset_at: datetime
    retry_after_seconds: float = 0.0


class Authorizer:
    """Authorize requests based on credentials and capabilities.

    Authorization rules:
    - Check capability requirements for methods
    - Apply rate limits per client
    - Support method-level permissions
    """

    # Default capability requirements for methods
    DEFAULT_METHOD_CAPABILITIES: dict[str, list[str]] = {
        "case.create": ["case:write"],
        "case.get": ["case:read"],
        "case.list": ["case:read"],
        "case.resume": ["case:write"],
        "flow.run": ["flow:execute"],
        "flow.resume": ["flow:execute"],
        "flow.step": ["flow:execute"],
        "flow.checkpoints": ["flow:read"],
        "skill.list": ["skill:read"],
        "skill.get": ["skill:read"],
        "tool.invoke": ["tool:invoke"],
        "tool.list": ["tool:read"],
        "gateway.subscribe": ["gateway:subscribe"],
        "gateway.unsubscribe": ["gateway:subscribe"],
        "gateway.publish": ["gateway:publish"],
        "system.list_methods": ["system:read"],
        "system.ping": ["system:read"],
    }

    def __init__(
        self,
        *,
        method_capabilities: dict[str, list[str]] | None = None,
        admin_capabilities: list[str] | None = None,
    ) -> None:
        self._method_caps = method_capabilities or self.DEFAULT_METHOD_CAPABILITIES
        self._admin_caps = admin_capabilities or ["admin"]

    def authorize(
        self,
        credentials: AuthCredentials,
        method: str,
    ) -> bool:
        """Check if credentials authorize a method."""
        # Admin bypass
        if self._is_admin(credentials):
            return True

        # Get required capabilities for method
        required = self._method_caps.get(method, [])

        # No requirements = allowed
        if not required:
            return True

        # Check if credentials have all required capabilities
        for cap in required:
            if not credentials.has_capability(cap):
                return False

        return True

    def _is_admin(self, credentials: AuthCredentials) -> bool:
        """Check if credentials have admin privileges."""
        for cap in self._admin_caps:
            if credentials.has_capability(cap):
                return True
        return False

    def get_required_capabilities(self, method: str) -> list[str]:
        """Get required capabilities for a method."""
        return self._method_caps.get(method, [])


@dataclass
class RateLimiter:
    """Rate limiting for gateway requests.

    Features:
    - Token bucket algorithm
    - Per-client limits
    - Configurable burst allowance
    """

    requests_per_minute: int = 60
    burst_size: int = 10
    _buckets: dict[str, dict[str, Any]] = field(default_factory=dict)

    def check(self, client_id: str) -> RateLimitResult:
        """Check rate limit for a client."""
        now = utc_now()
        bucket = self._buckets.get(client_id)

        if bucket is None:
            bucket = {
                "tokens": self.burst_size,
                "last_update": now,
            }
            self._buckets[client_id] = bucket

        # Refill tokens
        elapsed = (now - bucket["last_update"]).total_seconds()
        refill = elapsed * (self.requests_per_minute / 60.0)
        bucket["tokens"] = min(self.burst_size, bucket["tokens"] + refill)
        bucket["last_update"] = now

        # Check if allowed
        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return RateLimitResult(
                allowed=True,
                remaining=int(bucket["tokens"]),
                reset_at=now + timedelta(minutes=1),
            )

        # Calculate retry after
        tokens_needed = 1.0 - bucket["tokens"]
        retry_after = tokens_needed / (self.requests_per_minute / 60.0)

        return RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=now + timedelta(seconds=retry_after),
            retry_after_seconds=retry_after,
        )

    def reset(self, client_id: str) -> None:
        """Reset rate limit for a client."""
        self._buckets.pop(client_id, None)

    def reset_all(self) -> None:
        """Reset all rate limits."""
        self._buckets.clear()
