from __future__ import annotations

from typing import Any

from rootseeker.observability.redaction import redact_payload

__all__ = ["StructuredLogger"]


class StructuredLogger:
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def info(self, event: str, payload: dict[str, Any] | None = None) -> None:
        self._records.append({"level": "info", "event": event, "payload": redact_payload(payload or {})})

    def error(self, event: str, payload: dict[str, Any] | None = None) -> None:
        self._records.append({"level": "error", "event": event, "payload": redact_payload(payload or {})})

    def list_records(self) -> list[dict[str, Any]]:
        return list(self._records)
