from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rootseeker.channel_routing.models import OutboundTarget, ResolvedRoute

__all__ = ["resolve_outbound_target", "OutboundTargetResolver", "EndpointConfig"]


@dataclass
class EndpointConfig:
    """Configuration for an outbound endpoint."""

    channel: str
    url_template: str  # e.g., "https://feishu.cn/bot/{webhook_id}"
    headers: dict[str, str] = field(default_factory=dict)
    default_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundTargetResolver:
    """Resolve outbound targets from routes using configuration.

    Supports:
    - Static endpoint configuration
    - URL template interpolation
    - Channel-specific endpoint mapping
    """

    _configs: dict[str, EndpointConfig] = field(default_factory=dict)
    _default_timeout_seconds: float = 10.0

    def register(self, config: EndpointConfig) -> None:
        """Register an endpoint configuration for a channel."""
        self._configs[config.channel] = config

    def resolve(self, route: ResolvedRoute) -> OutboundTarget:
        """Resolve an outbound target from a route."""
        config = self._configs.get(route.channel)

        if config is None:
            # Fallback to default endpoint
            return self._build_default_target(route)

        # Build endpoint from template
        endpoint = self._interpolate_url(config.url_template, route)

        return OutboundTarget(
            channel=route.channel,
            endpoint=endpoint,
            team=route.team,
            metadata={
                "tenant": route.tenant,
                "priority": route.priority,
                "headers": dict(config.headers),
                **config.default_metadata,
                **route.labels,
            },
        )

    def _interpolate_url(self, template: str, route: ResolvedRoute) -> str:
        """Interpolate URL template with route values."""
        url = template
        url = url.replace("{channel}", route.channel)
        url = url.replace("{team}", route.team)
        url = url.replace("{tenant}", route.tenant)
        for key, value in route.labels.items():
            url = url.replace(f"{{{key}}}", value)
        return url

    def _build_default_target(self, route: ResolvedRoute) -> OutboundTarget:
        """Build default target when no config is registered."""
        # Default endpoints by channel type
        default_endpoints = {
            "webhook": f"https://webhook.example.com/{route.tenant}/{route.team}",
            "feishu": f"https://open.feishu.cn/open-apis/bot/v2/hook/{route.labels.get('webhook_id', 'default')}",
            "dingtalk": f"https://oapi.dingtalk.com/robot/send?access_token={route.labels.get('access_token', 'default')}",
            "wechat": f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={route.labels.get('key', 'default')}",
        }

        endpoint = default_endpoints.get(
            route.channel,
            f"https://notify.example.com/{route.channel}/{route.team}",
        )

        return OutboundTarget(
            channel=route.channel,
            endpoint=endpoint,
            team=route.team,
            metadata={
                "tenant": route.tenant,
                "priority": route.priority,
                **route.labels,
            },
        )


# Global resolver instance with default configuration
_default_resolver = OutboundTargetResolver()


def resolve_outbound_target(route: ResolvedRoute) -> OutboundTarget:
    """Resolve an outbound target from a route.

    Uses the global resolver with default configuration.
    For custom configuration, create an OutboundTargetResolver instance.
    """
    return _default_resolver.resolve(route)


def configure_default_resolver(configs: list[EndpointConfig]) -> None:
    """Configure the default resolver with endpoint configurations."""
    for config in configs:
        _default_resolver.register(config)
