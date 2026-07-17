from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = ["CronSchedule", "ScheduleParseError", "parse_schedule"]


class ScheduleParseError(ValueError):
    """Raised when a cron expression cannot be parsed by the minimal scheduler."""


@dataclass(frozen=True)
class CronSchedule:
    expression: str
    timezone: str = "UTC"

    def next_after(self, now: datetime) -> datetime:
        tz = _load_timezone(self.timezone)
        current = _normalize(now, tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
        minute, hour = _parse_expression(self.expression)

        for _ in range(60 * 24 * 366):
            if minute.matches(current.minute) and hour.matches(current.hour):
                return current.astimezone(UTC)
            current += timedelta(minutes=1)
        raise ScheduleParseError(f"cannot find next run for expression: {self.expression}")


@dataclass(frozen=True)
class _CronField:
    values: frozenset[int] | None

    def matches(self, value: int) -> bool:
        return self.values is None or value in self.values


def parse_schedule(expression: str, timezone: str = "UTC") -> CronSchedule:
    _load_timezone(timezone)
    _parse_expression(expression)
    return CronSchedule(expression=expression, timezone=timezone)


@lru_cache(maxsize=128)
def _parse_expression(expression: str) -> tuple[_CronField, _CronField]:
    aliases = {
        "@hourly": "0 * * * *",
        "@daily": "0 0 * * *",
        "@weekly": "0 0 * * 0",
    }
    expr = aliases.get(expression.strip(), expression.strip())
    parts = expr.split()
    if len(parts) != 5:
        raise ScheduleParseError(f"cron expression must have 5 fields: {expression}")
    return _parse_field(parts[0], 0, 59), _parse_field(parts[1], 0, 23)


def _parse_field(raw: str, minimum: int, maximum: int) -> _CronField:
    if raw == "*":
        return _CronField(values=None)
    if raw.startswith("*/"):
        step = _parse_int(raw[2:], minimum=1, maximum=maximum)
        return _CronField(values=frozenset(range(minimum, maximum + 1, step)))
    values = frozenset(
        _parse_int(part, minimum=minimum, maximum=maximum) for part in raw.split(",")
    )
    return _CronField(values=values)


def _parse_int(raw: str, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ScheduleParseError(f"invalid cron field value: {raw}") from exc
    if value < minimum or value > maximum:
        raise ScheduleParseError(f"cron field value out of range: {raw}")
    return value


def _load_timezone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleParseError(f"unknown timezone: {timezone}") from exc


def _normalize(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(tz)
