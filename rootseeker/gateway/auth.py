"""Gateway authentication middleware."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from rootseeker.contracts.common import utc_now

__all__ = ["AuthCredentials", "AuthProvider", "TokenAuthProvider"]


@dataclass
class AuthCredentials:
    """Authenticated credentials."""

    client_id: str
    token: str
    capabilities: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if credentials are expired."""
        if self.expires_at is None:
            return False
        return utc_now() > self.expires_at

    def has_capability(self, capability: str) -> bool:
        """Check if credentials have a specific capability."""
        if not self.capabilities:
            return True  # No capability restrictions
        return capability in self.capabilities


class AuthProvider(ABC):
    """Abstract authentication provider."""

    @abstractmethod
    def authenticate(self, token: str) -> AuthCredentials | None:
        """Authenticate a token and return credentials."""
        ...

    @abstractmethod
    def validate(self, credentials: AuthCredentials) -> bool:
        """Validate credentials are still valid."""
        ...


@dataclass
class TokenAuthProvider(AuthProvider):
    """Token-based authentication provider.

    Supports:
    - Static tokens (for development)
    - HMAC-signed tokens
    - Time-limited tokens
    """

    secret_key: str = "dev-secret-key"
    token_lifetime_seconds: int = 3600  # 1 hour
    _tokens: dict[str, AuthCredentials] = field(default_factory=dict)

    def generate_token(self, client_id: str, capabilities: list[str] | None = None) -> str:
        """Generate a new token for a client."""
        token = secrets.token_urlsafe(32)
        expires_at = utc_now() + timedelta(seconds=self.token_lifetime_seconds)

        credentials = AuthCredentials(
            client_id=client_id,
            token=token,
            capabilities=capabilities or [],
            expires_at=expires_at,
        )

        self._tokens[token] = credentials
        return token

    def authenticate(self, token: str) -> AuthCredentials | None:
        """Authenticate a token."""
        credentials = self._tokens.get(token)
        if credentials is None:
            return None

        if credentials.is_expired():
            self._tokens.pop(token, None)
            return None

        return credentials

    def validate(self, credentials: AuthCredentials) -> bool:
        """Validate credentials."""
        stored = self._tokens.get(credentials.token)
        if stored is None:
            return False

        if stored.is_expired():
            self._tokens.pop(credentials.token, None)
            return False

        return stored.client_id == credentials.client_id

    def revoke(self, token: str) -> bool:
        """Revoke a token."""
        if token in self._tokens:
            del self._tokens[token]
            return True
        return False

    def create_signed_token(self, client_id: str, capabilities: list[str] | None = None) -> str:
        """Create a HMAC-signed token."""
        timestamp = str(int(utc_now().timestamp()))
        payload = f"{client_id}:{timestamp}:{','.join(capabilities or [])}"
        signature = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{payload}:{signature}"

    def verify_signed_token(self, token: str) -> AuthCredentials | None:
        """Verify a HMAC-signed token."""
        parts = token.split(":")
        if len(parts) != 4:
            return None

        client_id, timestamp_str, caps_str, signature = parts

        # Verify signature
        payload = f"{client_id}:{timestamp_str}:{caps_str}"
        expected_sig = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Check timestamp
        try:
            timestamp = int(timestamp_str)
            token_time = datetime.fromtimestamp(timestamp, UTC)
            if utc_now() - token_time > timedelta(seconds=self.token_lifetime_seconds):
                return None
        except ValueError:
            return None

        capabilities = caps_str.split(",") if caps_str else []

        return AuthCredentials(
            client_id=client_id,
            token=token,
            capabilities=capabilities,
        )
