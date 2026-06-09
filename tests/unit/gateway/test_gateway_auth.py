from __future__ import annotations

from rootseeker.gateway.auth import TokenAuthProvider


def test_signed_token_verification_uses_timezone_aware_timestamp() -> None:
    provider = TokenAuthProvider(secret_key="secret")
    token = provider.create_signed_token("client-1", capabilities=["tool.invoke"])

    credentials = provider.verify_signed_token(token)

    assert credentials is not None
    assert credentials.client_id == "client-1"
    assert credentials.capabilities == ["tool.invoke"]
