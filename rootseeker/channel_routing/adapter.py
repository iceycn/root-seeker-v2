from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rootseeker.channel_routing.models import OutboundTarget

__all__ = ["ChannelAdapter", "ChannelRegistry", "SendResult"]


@dataclass
class SendResult:
    """Result of sending a notification through a channel."""

    ok: bool
    channel: str
    message: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(ABC):
    """Abstract base class for channel adapters."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return the channel name this adapter handles (e.g., 'wechat', 'feishu', 'webhook')."""
        ...

    @abstractmethod
    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send a notification to the target channel.

        Args:
            target: The outbound target containing endpoint and metadata.
            message: The message content to send.

        Returns:
            SendResult indicating success or failure.
        """
        ...


@dataclass
class ChannelRegistry:
    """Registry for channel adapters."""

    _adapters: dict[str, ChannelAdapter] = field(default_factory=dict)

    def register(self, adapter: ChannelAdapter) -> None:
        """Register a channel adapter."""
        self._adapters[adapter.channel_name] = adapter

    def get(self, channel: str) -> ChannelAdapter | None:
        """Get a channel adapter by channel name."""
        return self._adapters.get(channel)

    def has(self, channel: str) -> bool:
        """Check if a channel adapter is registered."""
        return channel in self._adapters

    def list_channels(self) -> list[str]:
        """List all registered channel names."""
        return list(self._adapters.keys())

    def send(self, target: OutboundTarget, message: str) -> SendResult:
        """Send a notification through the appropriate channel adapter.

        Args:
            target: The outbound target.
            message: The message to send.

        Returns:
            SendResult from the channel adapter, or an error result if no adapter found.
        """
        adapter = self.get(target.channel)
        if adapter is None:
            return SendResult(
                ok=False,
                channel=target.channel,
                message=message,
                error=f"no adapter registered for channel: {target.channel}",
            )
        return adapter.send(target, message)
