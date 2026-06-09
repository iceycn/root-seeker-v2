from __future__ import annotations

from rootseeker.channel_routing.channel import ChannelSpec

__all__ = ["ChannelRegistry"]


class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: dict[str, ChannelSpec] = {}

    def register(self, spec: ChannelSpec) -> None:
        self._channels[spec.channel_id] = spec

    def get(self, channel_id: str) -> ChannelSpec | None:
        return self._channels.get(channel_id)

    def list_all(self) -> list[ChannelSpec]:
        return list(self._channels.values())
