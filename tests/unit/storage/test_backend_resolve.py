from __future__ import annotations

from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.backend_resolve import (
    resolve_admin_store,
    resolve_cron_state_store,
    resolve_error_history_store,
)


def test_auto_follows_mysql_backend(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "mysql")
    monkeypatch.setenv("ROOTSEEKER_ADMIN_STORE", "auto")
    monkeypatch.setenv("ROOTSEEKER_CRON_STATE_STORE", "auto")
    monkeypatch.setenv("ROOTSEEKER_ERROR_HISTORY_STORE", "auto")
    settings = RootSeekerSettings()
    assert resolve_admin_store(settings) == "mysql"
    assert resolve_cron_state_store(settings) == "mysql"
    assert resolve_error_history_store(settings) == "mysql"


def test_auto_follows_sqlite_to_file(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("ROOTSEEKER_ADMIN_STORE", "auto")
    monkeypatch.setenv("ROOTSEEKER_CRON_STATE_STORE", "auto")
    monkeypatch.setenv("ROOTSEEKER_ERROR_HISTORY_STORE", "auto")
    settings = RootSeekerSettings()
    assert resolve_admin_store(settings) == "file"
    assert resolve_cron_state_store(settings) == "file"
    assert resolve_error_history_store(settings) == "file"


def test_explicit_overrides(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "mysql")
    monkeypatch.setenv("ROOTSEEKER_ADMIN_STORE", "file")
    monkeypatch.setenv("ROOTSEEKER_ERROR_HISTORY_STORE", "sqlite")
    settings = RootSeekerSettings()
    assert resolve_admin_store(settings) == "file"
    assert resolve_error_history_store(settings) == "sqlite"
