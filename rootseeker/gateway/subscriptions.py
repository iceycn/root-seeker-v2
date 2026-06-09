from __future__ import annotations

from collections import defaultdict

__all__ = ["SubscriptionRegistry", "topic_matches"]


class SubscriptionRegistry:
    def __init__(self) -> None:
        self._topic_clients: dict[str, set[str]] = defaultdict(set)
        self._client_topics: dict[str, set[str]] = defaultdict(set)

    def subscribe(self, client_id: str, topic: str) -> None:
        self._topic_clients[topic].add(client_id)
        self._client_topics[client_id].add(topic)

    def unsubscribe(self, client_id: str, topic: str) -> None:
        self._topic_clients[topic].discard(client_id)
        self._client_topics[client_id].discard(topic)

    def remove_client(self, client_id: str) -> None:
        topics = list(self._client_topics.get(client_id, set()))
        for topic in topics:
            self._topic_clients[topic].discard(client_id)
        self._client_topics.pop(client_id, None)

    def resolve_clients(self, topic: str) -> set[str]:
        matched: set[str] = set()
        for subscribed_topic, clients in self._topic_clients.items():
            if topic_matches(subscribed_topic, topic):
                matched.update(clients)
        return matched

    def list_topics(self, client_id: str) -> list[str]:
        return sorted(self._client_topics.get(client_id, set()))


def topic_matches(pattern: str, topic: str) -> bool:
    if pattern == topic:
        return True
    if pattern.endswith(".*"):
        return topic.startswith(pattern[:-1])
    return False
