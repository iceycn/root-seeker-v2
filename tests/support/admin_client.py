from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from apps.admin.main import create_app

TEST_ADMIN_USERNAME = "testadmin"
TEST_ADMIN_PASSWORD = "password12"


def make_admin_client(
    repo_root: Path,
    *,
    authenticated: bool = True,
    **kwargs: Any,
) -> TestClient:
    client = TestClient(create_app(repo_root, **kwargs), follow_redirects=False)
    if authenticated:
        resp = client.post(
            "/api/auth/bootstrap",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert resp.status_code == 200, resp.text
    return client


def bootstrap_client(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/bootstrap",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
