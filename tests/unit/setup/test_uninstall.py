from pathlib import Path

from scripts.uninstall import clean_local_artifacts, run_uninstall, stop_native_from_state


def test_clean_local_artifacts(tmp_path: Path) -> None:
    (tmp_path / ".tools").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "rootseeker.db").write_text("x", encoding="utf-8")
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".setup-state.json").write_text("{}", encoding="utf-8")
    clean_local_artifacts(tmp_path)
    assert not (tmp_path / ".tools").exists()
    assert not (tmp_path / ".venv").exists()
    assert not (tmp_path / ".env").exists()
    assert not (tmp_path / ".setup-state.json").exists()
    assert (tmp_path / "data").is_dir()
    assert list((tmp_path / "data").iterdir()) == []


def test_stop_native_from_state(tmp_path: Path, monkeypatch) -> None:
    killed: list[int] = []
    monkeypatch.setattr("scripts.uninstall._kill_pid", lambda pid: killed.append(pid))
    (tmp_path / ".setup-state.json").write_text(
        '{"version":1,"steps":{"app_up":{"done":true,"meta":{"api_pid":111,"admin_pid":222}}}}',
        encoding="utf-8",
    )
    stop_native_from_state(tmp_path)
    assert killed == [111, 222]


def test_run_uninstall_invokes_cleanup(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("scripts.uninstall.stop_native_from_state", lambda root: calls.append("native"))
    monkeypatch.setattr(
        "scripts.setup.portable_mysql.stop_portable_mysql",
        lambda root: calls.append("mysql"),
    )
    monkeypatch.setattr("scripts.uninstall.stop_docker_stack", lambda root: calls.append("docker"))
    monkeypatch.setattr("scripts.uninstall.clean_local_artifacts", lambda root: calls.append("clean"))
    assert run_uninstall(tmp_path) == 0
    assert calls == ["native", "mysql", "docker", "clean"]
