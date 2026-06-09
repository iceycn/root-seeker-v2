"""Tests for notify URL resolution from environment."""

from __future__ import annotations

import pytest

from rootseeker.channel_routing.notify_env import resolve_notify_outbound_target


@pytest.fixture(autouse=True)
def cleared_notify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        "ROOTSEEKER_NOTIFY_DEFAULT_URL",
        "ROOTSEEKER_NOTIFY_WECHAT_WORK_URL",
        "WECHAT_WORK_WEBHOOK_URL",
        "ROOTSEEKER_NOTIFY_FEISHU_URL",
        "FEISHU_WEBHOOK_URL",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_wechat_work_prefers_rootseeker_notify_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ROOTSEEKER_NOTIFY_WECHAT_WORK_URL",
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=rootseeker-key",
    )
    target = resolve_notify_outbound_target("wechat_work")
    assert target is not None
    assert "rootseeker-key" in target.endpoint


def test_wechat_work_fallback_to_wechat_work_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "WECHAT_WORK_WEBHOOK_URL",
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=legacy-key",
    )
    target = resolve_notify_outbound_target("wechat_work")
    assert target is not None
    assert "legacy-key" in target.endpoint


def test_resolve_returns_none_when_unconfigured() -> None:
    target = resolve_notify_outbound_target("wechat_work")
    assert target is None


def test_default_url_used_when_specific_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_NOTIFY_DEFAULT_URL", "https://hooks.example.com/x")
    target = resolve_notify_outbound_target("wechat_work")
    assert target is not None
    assert target.endpoint == "https://hooks.example.com/x"


def test_feishu_legacy_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROOTSEEKER_NOTIFY_FEISHU_URL", raising=False)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/xyz")
    target = resolve_notify_outbound_target("feishu")
    assert target is not None
    assert "feishu" in target.endpoint
