"""Unit tests for AdminConfigStore cron_jobs CRUD and builtin seed."""

from __future__ import annotations

import pytest

from apps.admin.config_store import (
    BUILTIN_CRON_JOBS,
    REPO_SYNC_CHANGED_JOB_ID,
    AdminConfigStore,
)


def test_load_seeds_builtin_cron_jobs(tmp_path) -> None:
    store = AdminConfigStore(tmp_path / "config.json")
    jobs = store.list_cron_jobs()
    ids = {item["job_id"] for item in jobs}
    assert REPO_SYNC_CHANGED_JOB_ID in ids
    builtin = next(item for item in jobs if item["job_id"] == REPO_SYNC_CHANGED_JOB_ID)
    assert builtin["handler"] == "repo.sync_changed"
    assert builtin["schedule"] == "@hourly"
    assert builtin["enabled"] is True
    assert builtin["builtin"] is True
    assert builtin["deletable"] is False
    assert "GitNexus" in str(builtin.get("notes") or "")
    assert len(jobs) >= len(BUILTIN_CRON_JOBS)


def test_cannot_delete_builtin_cron_job(tmp_path) -> None:
    store = AdminConfigStore(tmp_path / "config.json")
    with pytest.raises(ValueError, match="cannot be deleted"):
        store.delete_cron_job(REPO_SYNC_CHANGED_JOB_ID)


def test_upsert_custom_and_update_builtin_schedule(tmp_path) -> None:
    store = AdminConfigStore(tmp_path / "config.json")
    custom = store.upsert_cron_job(
        {
            "name": "全量同步",
            "handler": "repo.sync_all",
            "schedule": "0 3 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": False,
        }
    )
    assert custom["job_id"].startswith("cron.")
    assert custom["builtin"] is False

    updated = store.upsert_cron_job(
        {
            "job_id": REPO_SYNC_CHANGED_JOB_ID,
            "schedule": "15 * * * *",
            "enabled": False,
            "name": "仓库增量同步(自定义)",
        }
    )
    assert updated["schedule"] == "15 * * * *"
    assert updated["enabled"] is False
    assert updated["handler"] == "repo.sync_changed"
    assert updated["builtin"] is True

    store.delete_cron_job(custom["job_id"])
    assert store.get_cron_job(custom["job_id"]) is None
