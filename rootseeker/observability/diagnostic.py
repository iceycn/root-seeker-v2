from __future__ import annotations

from typing import Any

from rootseeker.observability.logger import StructuredLogger

__all__ = ["DiagnosticCollector"]


class DiagnosticCollector:
    def __init__(self, logger: StructuredLogger) -> None:
        self._logger = logger

    def record(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self._logger.info(f"diagnostic.{name}", payload or {})
