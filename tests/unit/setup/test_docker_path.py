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


def test_docker_path_build_fail_falls_back_to_pull(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "docker-compose.pull.yml").write_text("services: {}\n", encoding="utf-8")
    state = SetupState()
    cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        cmds.append([str(c) for c in cmd])
        if "build" in cmd:
            return MagicMock(returncode=1)
        return MagicMock(returncode=0)

    monkeypatch.setattr("scripts.setup.docker_path.merge_env_file", lambda *a, **k: None)
    monkeypatch.setattr("scripts.setup.docker_path._prepare_zoekt", lambda _root: None)
    monkeypatch.setattr("scripts.setup.docker_path.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.setup.docker_path.wait_http_ok", lambda *a, **k: True)
    monkeypatch.setattr("scripts.setup.docker_path._image_present", lambda _name: True)

    code = run_docker_path(
        tmp_path,
        build_only=False,
        storage="mysql",
        state=state,
        noninteractive=True,
    )
    assert code == 0
    joined = [" ".join(c) for c in cmds]
    assert any("build" in j for j in joined)
    assert any("docker-compose.pull.yml" in j and "up" in j for j in joined)
