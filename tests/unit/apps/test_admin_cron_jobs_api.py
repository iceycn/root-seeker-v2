"""Admin cron-jobs API tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.admin.config_store import REPO_SYNC_CHANGED_JOB_ID
from apps.admin.main import create_app
from rootseeker.cron import JobRunResult, JobRunStatus


def _client(tmp_path: Path) -> TestClient:
    app = create_app(repo_root=tmp_path)
    return TestClient(app)


def test_cron_jobs_list_includes_builtin(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/cron-jobs")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["job_id"] for item in data["items"]}
    assert REPO_SYNC_CHANGED_JOB_ID in ids
    assert "repo.sync_changed" in data["handlers"]


def test_cron_jobs_crud_and_delete_builtin_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    create = client.post(
        "/api/cron-jobs",
        json={
            "name": "夜间全量",
            "handler": "repo.sync_all",
            "schedule": "0 2 * * *",
            "enabled": True,
        },
    )
    assert create.status_code == 200
    job_id = create.json()["job"]["job_id"]

    update = client.put(f"/api/cron-jobs/{job_id}", json={"enabled": False})
    assert update.status_code == 200
    assert update.json()["job"]["enabled"] is False

    forbidden = client.delete(f"/api/cron-jobs/{REPO_SYNC_CHANGED_JOB_ID}")
    assert forbidden.status_code == 400

    deleted = client.delete(f"/api/cron-jobs/{job_id}")
    assert deleted.status_code == 200


def test_cron_jobs_run_endpoint(tmp_path: Path) -> None:
    client = _client(tmp_path)
    fake = JobRunResult(
        job_id=REPO_SYNC_CHANGED_JOB_ID,
        status=JobRunStatus.SUCCEEDED,
        message="",
        payload={"changed": [], "synced": [], "skipped": []},
    )
    with patch("apps.admin.main.run_job_now", return_value=fake) as mocked:
        resp = client.post(f"/api/cron-jobs/{REPO_SYNC_CHANGED_JOB_ID}/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["started"] is True
    mocked.assert_called_once()
