from __future__ import annotations

from datetime import timedelta

from rootseeker.contracts.common import utc_now

__all__ = ["resolve_time_window"]


def resolve_time_window(*, lookback_minutes: int = 15) -> tuple[str, str]:
    end = utc_now()
    start = end - timedelta(minutes=max(1, lookback_minutes))
    return start.isoformat(), end.isoformat()
