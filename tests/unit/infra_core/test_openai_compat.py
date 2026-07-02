from __future__ import annotations

from rootseeker.infra_core.openai_compat import (
    MIMO_PAYG_BASE_URL,
    MIMO_TOKEN_PLAN_CN_OPENAI_BASE_URL,
    is_mimo_token_plan_key,
    resolve_mimo_base_url,
)


def test_resolve_mimo_token_plan_key_uses_cn_cluster() -> None:
    assert resolve_mimo_base_url(
        api_key="tp-test-key",
        base_url="https://api.mimo.mi.com/v1",
    ) == MIMO_TOKEN_PLAN_CN_OPENAI_BASE_URL


def test_resolve_mimo_payg_key_uses_public_api() -> None:
    assert resolve_mimo_base_url(
        api_key="sk-test-key",
        base_url="https://api.mimo.mi.com/v1",
    ) == MIMO_PAYG_BASE_URL


def test_resolve_mimo_keeps_custom_token_plan_url() -> None:
    custom = "https://token-plan-sgp.xiaomimimo.com/v1"
    assert resolve_mimo_base_url(api_key="tp-test-key", base_url=custom) == custom


def test_is_mimo_token_plan_key() -> None:
    assert is_mimo_token_plan_key("tp-abc") is True
    assert is_mimo_token_plan_key("sk-abc") is False
