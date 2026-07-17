from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from rootseeker.channel_routing.adapter import ChannelAdapter, SendResult
from rootseeker.channel_routing.models import OutboundTarget

__all__ = [
    "RecordingChannelAdapter",
    "WebhookChannelAdapter",
    "FeishuChannelAdapter",
    "DingTalkChannelAdapter",
    "WeChatWorkAdapter",
    "SlackChannelAdapter",
    "DiscordChannelAdapter",
]


@dataclass
class RecordingChannelAdapter(ChannelAdapter):
    """Records outbound payloads in memory; for tests — not wired into the default registry."""

    _channel_name: str = "recording"
    _sent_messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        record = {
            "channel": target.channel,
            "endpoint": target.endpoint,
            "team": target.team,
            "message": message,
            "metadata": dict(target.metadata),
        }
        self._sent_messages.append(record)
        return SendResult(
            ok=True,
            channel=target.channel,
            message=message,
            metadata={"record": record},
        )

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Return all sent messages (for testing)."""
        return list(self._sent_messages)

    def clear(self) -> None:
        """Clear sent messages history."""
        self._sent_messages.clear()


@dataclass
class WebhookChannelAdapter(ChannelAdapter):
    """Webhook channel adapter for HTTP callbacks.

    Sends HTTP POST requests to the configured endpoint URL.
    Supports custom headers and timeout configuration.
    """

    _channel_name: str = "webhook"
    _timeout_seconds: float = 10.0
    _headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send notification via HTTP POST to the endpoint URL."""
        payload = {
            "message": message,
            "channel": target.channel,
            "team": target.team,
            **target.metadata,
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    target.endpoint,
                    json=payload,
                    headers={**self._headers, **target.metadata.get("headers", {})},
                )

                ok = 200 <= response.status_code < 300
                return SendResult(
                    ok=ok,
                    channel=target.channel,
                    message=message,
                    error=None if ok else f"HTTP {response.status_code}: {response.text[:200]}",
                    metadata={
                        "endpoint": target.endpoint,
                        "status_code": response.status_code,
                        "response_body": response.text[:500] if response.text else None,
                    },
                )
        except httpx.TimeoutException:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error="Request timeout",
            )
        except httpx.RequestError as e:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=f"Request error: {e}",
            )


@dataclass
class FeishuChannelAdapter(ChannelAdapter):
    """Feishu (Lark) webhook adapter.

    Sends messages to Feishu bot webhooks.
    Supports text, post, and interactive message types.
    """

    _channel_name: str = "feishu"
    _timeout_seconds: float = 10.0

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send message to Feishu webhook."""
        # Feishu webhook expects specific format
        msg_type = target.metadata.get("msg_type", "text")
        payload = {
            "msg_type": msg_type,
            "content": self._build_content(msg_type, message, target.metadata),
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(target.endpoint, json=payload)
                result = response.json()

                ok = result.get("StatusCode") == 0 or result.get("code") == 0
                return SendResult(
                    ok=ok,
                    channel=target.channel,
                    message=message,
                    error=result.get("msg") if not ok else None,
                    metadata={"response": result},
                )
        except Exception as e:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=str(e),
            )

    def _build_content(
        self, msg_type: str, message: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Build Feishu message content based on type."""
        if msg_type == "text":
            return {"text": message}
        if msg_type == "post":
            return {
                "post": {
                    "zh_cn": {
                        "title": metadata.get("title", "Notification"),
                        "content": [[{"tag": "text", "text": message}]],
                    }
                }
            }
        return {"text": message}


@dataclass
class DingTalkChannelAdapter(ChannelAdapter):
    """DingTalk webhook adapter.

    Sends messages to DingTalk bot webhooks.
    Supports text, markdown, and link message types.
    """

    _channel_name: str = "dingtalk"
    _timeout_seconds: float = 10.0

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send message to DingTalk webhook."""
        msg_type = target.metadata.get("msg_type", "text")
        payload = {
            "msgtype": msg_type,
            msg_type: self._build_content(msg_type, message, target.metadata),
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(target.endpoint, json=payload)
                result = response.json()

                ok = result.get("errcode") == 0
                return SendResult(
                    ok=ok,
                    channel=target.channel,
                    message=message,
                    error=result.get("errmsg") if not ok else None,
                    metadata={"response": result},
                )
        except Exception as e:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=str(e),
            )

    def _build_content(
        self, msg_type: str, message: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Build DingTalk message content based on type."""
        if msg_type == "text":
            return {"content": message}
        if msg_type == "markdown":
            return {
                "title": metadata.get("title", "Notification"),
                "text": message,
            }
        if msg_type == "link":
            return {
                "title": metadata.get("title", "Notification"),
                "text": message,
                "messageUrl": metadata.get("url", ""),
            }
        return {"content": message}


@dataclass
class WeChatWorkAdapter(ChannelAdapter):
    """WeChat Work (企业微信) webhook adapter.

    Sends messages to WeChat Work bot webhooks.
    Supports text, markdown, and image message types.
    """

    _channel_name: str = "wechat_work"
    _timeout_seconds: float = 10.0

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send message to WeChat Work webhook."""
        msg_type = target.metadata.get("msg_type", "text")
        payload = {
            "msgtype": msg_type,
            msg_type: self._build_content(msg_type, message, target.metadata),
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(target.endpoint, json=payload)
                result = response.json()

                ok = result.get("errcode") == 0
                return SendResult(
                    ok=ok,
                    channel=target.channel,
                    message=message,
                    error=result.get("errmsg") if not ok else None,
                    metadata={"response": result},
                )
        except Exception as e:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=str(e),
            )

    def _build_content(
        self, msg_type: str, message: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Build WeChat Work message content based on type."""
        if msg_type == "text":
            return {"content": message}
        if msg_type == "markdown":
            return {"content": message}
        if msg_type == "image":
            return {
                "base64": metadata.get("base64", ""),
                "md5": metadata.get("md5", ""),
            }
        return {"content": message}


@dataclass
class SlackChannelAdapter(ChannelAdapter):
    """Slack webhook adapter.

    Sends messages to Slack incoming webhooks.
    Supports text and block kit message formats.
    """

    _channel_name: str = "slack"
    _timeout_seconds: float = 10.0

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send message to Slack webhook."""
        # Check if blocks are provided
        blocks = target.metadata.get("blocks")
        if blocks:
            payload = {"blocks": blocks, "text": message}
        else:
            payload = {"text": message}

        # Add channel if specified
        if "channel" in target.metadata:
            payload["channel"] = target.metadata["channel"]

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(target.endpoint, json=payload)

                # Slack returns "ok" on success
                ok = response.status_code == 200 and response.text == "ok"
                return SendResult(
                    ok=ok,
                    channel=target.channel,
                    message=message,
                    error=None if ok else f"HTTP {response.status_code}",
                    metadata={"status_code": response.status_code},
                )
        except Exception as e:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=str(e),
            )


@dataclass
class DiscordChannelAdapter(ChannelAdapter):
    """Discord webhook adapter.

    Sends messages to Discord channel webhooks.
    Supports text and embed message formats.
    """

    _channel_name: str = "discord"
    _timeout_seconds: float = 10.0

    @property
    def channel_name(self) -> str:
        return self._channel_name

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send message to Discord webhook."""
        # Check if embeds are provided
        embeds = target.metadata.get("embeds")
        if embeds:
            payload = {"embeds": embeds}
        else:
            payload = {"content": message}

        # Add username if specified
        if "username" in target.metadata:
            payload["username"] = target.metadata["username"]

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(target.endpoint, json=payload)

                # Discord returns 204 No Content on success
                ok = response.status_code in (200, 204)
                return SendResult(
                    ok=ok,
                    channel=target.channel,
                    message=message,
                    error=None if ok else f"HTTP {response.status_code}",
                    metadata={"status_code": response.status_code},
                )
        except Exception as e:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=str(e),
            )
