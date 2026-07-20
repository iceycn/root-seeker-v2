"""Helpers for resolving storage sub-backends from settings."""

from __future__ import annotations

from typing import Literal

from rootseeker.infra_core.settings import RootSeekerSettings

__all__ = [
    "resolve_admin_store",
    "resolve_cron_state_store",
    "resolve_error_history_store",
]


def resolve_admin_store(settings: RootSeekerSettings) -> Literal["file", "mysql"]:
    if settings.admin_store == "mysql":
        return "mysql"
    if settings.admin_store == "file":
        return "file"
    return "mysql" if settings.storage_backend == "mysql" else "file"


def resolve_cron_state_store(settings: RootSeekerSettings) -> Literal["file", "mysql"]:
    if settings.cron_state_store == "mysql":
        return "mysql"
    if settings.cron_state_store == "file":
        return "file"
    return "mysql" if settings.storage_backend == "mysql" else "file"


def resolve_error_history_store(
    settings: RootSeekerSettings,
) -> Literal["file", "sqlite", "mysql"]:
    if settings.error_history_store in ("file", "sqlite", "mysql"):
        return settings.error_history_store  # type: ignore[return-value]
    return "mysql" if settings.storage_backend == "mysql" else "file"
