from pathlib import Path
from unittest.mock import MagicMock

from scripts.setup.docker_path import run_docker_path
from scripts.setup.state import SetupState


def test_docker_path_writes_mysql_env(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env.docker").write_text("FOO=1\n", encoding="utf-8")
    state = SetupState()
    calls: list[dict] = []

    def fake_merge(path, updates, overwrite_existing=False):  # noqa: ANN001
        calls.append(dict(updates))

    monkeypatch.setattr("scripts.setup.docker_path.merge_env_file", fake_merge)
    monkeypatch.setattr("scripts.setup.docker_path._prepare_zoekt", lambda _root: None)
    monkeypatch.setattr(
        "scripts.setup.docker_path.subprocess.run",
        lambda *a, **k: MagicMock(returncode=0),
    )
    monkeypatch.setattr("scripts.setup.docker_path.wait_http_ok", lambda *a, **k: True)

    code = run_docker_path(
        tmp_path,
        build_only=True,
        storage="mysql",
        state=state,
        noninteractive=True,
    )
    assert code == 0
    assert any(c.get("ROOTSEEKER_STORAGE_BACKEND") == "mysql" for c in calls)
    assert any(c.get("COMPOSE_PROFILES") == "mysql" for c in calls)


def test_docker_path_sqlite_clears_profile(tmp_path: Path, monkeypatch) -> None:
    state = SetupState()
    calls: list[dict] = []
    monkeypatch.setattr(
        "scripts.setup.docker_path.merge_env_file",
        lambda path, updates, overwrite_existing=False: calls.append(dict(updates)),
    )
    monkeypatch.setattr("scripts.setup.docker_path._prepare_zoekt", lambda _root: None)
    monkeypatch.setattr(
        "scripts.setup.docker_path.subprocess.run",
        lambda *a, **k: MagicMock(returncode=0),
    )
    monkeypatch.setattr("scripts.setup.docker_path.wait_http_ok", lambda *a, **k: True)
    run_docker_path(
        tmp_path,
        build_only=True,
        storage="sqlite",
        state=state,
        noninteractive=True,
    )
    assert any(c.get("COMPOSE_PROFILES") == "" for c in calls)
