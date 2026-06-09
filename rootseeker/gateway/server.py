from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from rootseeker.gateway.auth import AuthProvider
from rootseeker.gateway.authorizer import Authorizer, RateLimiter
from rootseeker.gateway.broadcaster import GatewayBroadcaster
from rootseeker.gateway.connection import GatewayConnection
from rootseeker.gateway.errors import GatewayError, GatewayValidationError
from rootseeker.gateway.event_sink import InMemoryEventSink
from rootseeker.gateway.method_registry import GatewayMethodRegistry
from rootseeker.gateway.protocol import GatewayEventFrame, GatewayRequestFrame, GatewayResponseFrame
from rootseeker.gateway.subscriptions import SubscriptionRegistry

__all__ = ["GatewayServer"]


class GatewayServer:
    def __init__(
        self,
        runtime: Any = None,
        *,
        auth_provider: AuthProvider | None = None,
        authorizer: Authorizer | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.connections: dict[str, GatewayConnection] = {}
        self.subscriptions = SubscriptionRegistry()
        self.sink = InMemoryEventSink()
        self.methods = GatewayMethodRegistry()
        self.broadcaster = GatewayBroadcaster(
            connections=self.connections,
            subscriptions=self.subscriptions,
            sink=self.sink,
        )
        self._runtime = runtime
        self._auth_provider = auth_provider
        self._authorizer = authorizer or Authorizer()
        self._rate_limiter = rate_limiter
        self._register_builtin_methods()
        if runtime is not None:
            self._register_business_methods(runtime)

    def connect(self, *, capabilities: list[str] | None = None) -> GatewayConnection:
        connection = GatewayConnection()
        connection.capabilities = set(capabilities or [])
        self.connections[connection.client_id] = connection
        return connection

    def disconnect(self, client_id: str) -> None:
        self.subscriptions.remove_client(client_id)
        self.connections.pop(client_id, None)

    def handle_http_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            frame = GatewayRequestFrame.model_validate(payload)
        except ValidationError as exc:
            err = GatewayValidationError(str(exc))
            return self._error_response(request_id=payload.get("request_id", "unknown"), err=err).model_dump(
                mode="json"
            )
        return self.handle_request(frame).model_dump(mode="json")

    def handle_request(self, frame: GatewayRequestFrame) -> GatewayResponseFrame:
        try:
            self._check_security(frame)
            result = self.methods.invoke(frame.method, frame.params)
            return GatewayResponseFrame(request_id=frame.request_id, ok=True, result=result)
        except GatewayError as err:
            return self._error_response(request_id=frame.request_id, err=err)
        except Exception as exc:  # noqa: BLE001
            err = GatewayError(str(exc))
            return self._error_response(request_id=frame.request_id, err=err)

    def _check_security(self, frame: GatewayRequestFrame) -> None:
        client_id = frame.client_id or "anonymous"
        if self._rate_limiter is not None:
            rate = self._rate_limiter.check(client_id)
            if not rate.allowed:
                raise GatewayError(
                    f"rate limit exceeded; retry after {rate.retry_after_seconds:.2f}s",
                    code="rate_limited",
                )
        if self._auth_provider is None:
            return
        token = str(frame.params.get("token") or "")
        credentials = self._auth_provider.authenticate(token)
        if credentials is None or not self._auth_provider.validate(credentials):
            raise GatewayError("authentication failed", code="unauthorized")
        if not self._authorizer.authorize(credentials, frame.method):
            raise GatewayError("permission denied", code="forbidden")

    def publish(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = GatewayEventFrame(topic=topic, payload=payload)
        result = self.broadcaster.broadcast(event)
        return {
            "topic": result.topic,
            "delivered_count": result.delivered_count,
            "dropped_clients": result.dropped_clients,
        }

    def poll_events(self, client_id: str, *, clear: bool = True) -> list[dict[str, Any]]:
        connection = self.connections.get(client_id)
        if connection is None:
            return []
        events = [event.model_dump(mode="json") for event in connection.inbox]
        if clear:
            connection.inbox.clear()
        return events

    def _register_builtin_methods(self) -> None:
        self.methods.register("system.ping", lambda _p: {"pong": True})
        self.methods.register("system.list_methods", lambda _p: {"items": self.methods.list_methods()})
        self.methods.register("gateway.subscribe", self._method_subscribe)
        self.methods.register("gateway.unsubscribe", self._method_unsubscribe)
        self.methods.register("gateway.publish", self._method_publish)

    def _register_business_methods(self, runtime: Any) -> None:
        """Register business methods (case/flow/skill/tool)."""
        from rootseeker.gateway.methods import register_all_business_methods

        register_all_business_methods(self.methods, runtime)

    def _method_subscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        client_id = str(params.get("client_id", ""))
        topic = str(params.get("topic", ""))
        if not client_id or not topic:
            raise GatewayValidationError("client_id and topic are required")
        if client_id not in self.connections:
            raise GatewayValidationError(f"unknown client_id: {client_id}")
        self.subscriptions.subscribe(client_id, topic)
        self.connections[client_id].subscriptions.add(topic)
        return {"client_id": client_id, "topics": self.subscriptions.list_topics(client_id)}

    def _method_unsubscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        client_id = str(params.get("client_id", ""))
        topic = str(params.get("topic", ""))
        if not client_id or not topic:
            raise GatewayValidationError("client_id and topic are required")
        self.subscriptions.unsubscribe(client_id, topic)
        conn = self.connections.get(client_id)
        if conn is not None:
            conn.subscriptions.discard(topic)
        return {"client_id": client_id, "topics": self.subscriptions.list_topics(client_id)}

    def _method_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        topic = str(params.get("topic", ""))
        payload = params.get("payload", {})
        if not topic or not isinstance(payload, dict):
            raise GatewayValidationError("topic and payload are required")
        return self.publish(topic, payload)

    @staticmethod
    def _error_response(*, request_id: str, err: GatewayError) -> GatewayResponseFrame:
        return GatewayResponseFrame(
            request_id=request_id,
            ok=False,
            error={"code": err.code, "message": err.message},
        )
