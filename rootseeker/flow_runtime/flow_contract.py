from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rootseeker.contracts.common import utc_now
from rootseeker.contracts.flow import FlowSpec

__all__ = ["FlowRun"]


@dataclass
class FlowRun:
    flow_spec: FlowSpec
    started_at: str = field(default_factory=lambda: utc_now().isoformat())
    status: str = "running"
    outputs: dict[str, Any] = field(default_factory=dict)
