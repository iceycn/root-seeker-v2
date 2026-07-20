from pathlib import Path

from scripts.setup.detect import detect_environment


def test_detect_docker_daemon_false_when_cli_missing(monkeypatch) -> None:
    monkeypatch.setattr("scripts.setup.detect.shutil.which", lambda _: None)
    info = detect_environment(Path("."))
    assert info.docker_cli is False
    assert info.docker_daemon is False


def test_python_ok_flag_present() -> None:
    info = detect_environment(Path("."))
    assert isinstance(info.python_ok, bool)
    assert info.python_version
