from __future__ import annotations

from rootseeker.channel_routing import (
    ChannelRegistry,
    OutboundTarget,
    RecordingChannelAdapter,
    WebhookChannelAdapter,
    send_outbound_notification,
)


def test_recording_channel_adapter_send() -> None:
    adapter = RecordingChannelAdapter()
    target = OutboundTarget(channel="recording", endpoint="test://endpoint", team="test-team")
    result = adapter.send(target, "test message")

    assert result.ok
    assert result.channel == "recording"
    assert result.message == "test message"
    assert result.error is None

    messages = adapter.get_sent_messages()
    assert len(messages) == 1
    assert messages[0]["message"] == "test message"


def test_recording_channel_adapter_clear() -> None:
    adapter = RecordingChannelAdapter()
    target = OutboundTarget(channel="recording", endpoint="test://endpoint", team="test-team")
    adapter.send(target, "msg1")
    adapter.send(target, "msg2")
    assert len(adapter.get_sent_messages()) == 2

    adapter.clear()
    assert len(adapter.get_sent_messages()) == 0


def test_webhook_channel_adapter_send() -> None:
    """Test webhook channel adapter with mocked HTTP."""
    from unittest.mock import MagicMock, patch

    adapter = WebhookChannelAdapter()
    target = OutboundTarget(
        channel="webhook",
        endpoint="https://example.com/webhook",
        team="test-team",
        metadata={"token": "abc123"},
    )

    # Mock httpx.Client to avoid real network calls
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = adapter.send(target, "webhook message")

        assert result.ok
        assert result.channel == "webhook"
        assert result.message == "webhook message"


def test_channel_registry_register_and_get() -> None:
    registry = ChannelRegistry()
    adapter = RecordingChannelAdapter()
    registry.register(adapter)

    assert registry.has("recording")
    assert registry.get("recording") is adapter
    assert registry.list_channels() == ["recording"]


def test_channel_registry_send() -> None:
    registry = ChannelRegistry()
    adapter = RecordingChannelAdapter()
    registry.register(adapter)

    target = OutboundTarget(channel="recording", endpoint="test://endpoint", team="test-team")
    result = registry.send(target, "registry message")

    assert result.ok
    assert result.channel == "recording"
    assert len(adapter.get_sent_messages()) == 1


def test_channel_registry_send_unknown_channel() -> None:
    registry = ChannelRegistry()
    target = OutboundTarget(channel="unknown", endpoint="test://endpoint", team="test-team")
    result = registry.send(target, "test")

    assert not result.ok
    assert result.error == "no adapter registered for channel: unknown"


def test_send_outbound_notification_with_registry() -> None:
    registry = ChannelRegistry()
    adapter = RecordingChannelAdapter()
    registry.register(adapter)

    target = OutboundTarget(channel="recording", endpoint="test://endpoint", team="test-team")
    result = send_outbound_notification(target, "outbound message", registry=registry)

    assert result["ok"]
    assert result["channel"] == "recording"
    assert len(adapter.get_sent_messages()) == 1


def test_send_outbound_notification_default_registry() -> None:
    """Default registry uses HTTPS-backed adapters — exercise webhook via patched HTTP."""
    from unittest.mock import MagicMock, patch

    target = OutboundTarget(
        channel="webhook",
        endpoint="https://example.com/webhook",
        team="test-team",
    )
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = send_outbound_notification(target, "default registry message")

        assert result["ok"]
        assert result["channel"] == "webhook"


def test_feishu_channel_adapter_send() -> None:
    """Test Feishu channel adapter with mocked HTTP."""
    from unittest.mock import MagicMock, patch

    from rootseeker.channel_routing import FeishuChannelAdapter

    adapter = FeishuChannelAdapter()
    target = OutboundTarget(
        channel="feishu",
        endpoint="https://open.feishu.cn/open-apis/bot/v2/hook/test",
        team="test-team",
    )

    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "msg": "success"}

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = adapter.send(target, "feishu message")

        assert result.ok
        assert result.channel == "feishu"
        assert result.message == "feishu message"


def test_dingtalk_channel_adapter_send() -> None:
    """Test DingTalk channel adapter with mocked HTTP."""
    from unittest.mock import MagicMock, patch

    from rootseeker.channel_routing import DingTalkChannelAdapter

    adapter = DingTalkChannelAdapter()
    target = OutboundTarget(
        channel="dingtalk",
        endpoint="https://oapi.dingtalk.com/robot/send?access_token=test",
        team="test-team",
    )

    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = adapter.send(target, "dingtalk message")

        assert result.ok
        assert result.channel == "dingtalk"
        assert result.message == "dingtalk message"


def test_wechat_work_adapter_send() -> None:
    """Test WeChat Work adapter with mocked HTTP."""
    from unittest.mock import MagicMock, patch

    from rootseeker.channel_routing import WeChatWorkAdapter

    adapter = WeChatWorkAdapter()
    target = OutboundTarget(
        channel="wechat_work",
        endpoint="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        team="test-team",
    )

    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = adapter.send(target, "wechat work message")

        assert result.ok
        assert result.channel == "wechat_work"
        assert result.message == "wechat work message"


def test_slack_channel_adapter_send() -> None:
    """Test Slack channel adapter with mocked HTTP."""
    from unittest.mock import MagicMock, patch

    from rootseeker.channel_routing import SlackChannelAdapter

    adapter = SlackChannelAdapter()
    target = OutboundTarget(
        channel="slack",
        endpoint="https://hooks.slack.com/services/test",
        team="test-team",
    )

    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = adapter.send(target, "slack message")

        assert result.ok
        assert result.channel == "slack"
        assert result.message == "slack message"


def test_discord_channel_adapter_send() -> None:
    """Test Discord channel adapter with mocked HTTP."""
    from unittest.mock import MagicMock, patch

    from rootseeker.channel_routing import DiscordChannelAdapter

    adapter = DiscordChannelAdapter()
    target = OutboundTarget(
        channel="discord",
        endpoint="https://discord.com/api/webhooks/test",
        team="test-team",
    )

    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 204

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.post.return_value = mock_response
        mock_client.return_value = mock_context

        result = adapter.send(target, "discord message")

        assert result.ok
        assert result.channel == "discord"
        assert result.message == "discord message"
