from pathlib import Path

from scripts.setup.state import SetupState


def test_mark_done_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / ".setup-state.json"
    s = SetupState()
    s.mark_done("detect", {"os": "windows"})
    s.save(path)
    loaded = SetupState.load(path)
    assert loaded.is_done("detect")
    assert loaded.meta("detect")["os"] == "windows"


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    loaded = SetupState.load(tmp_path / "missing.json")
    assert not loaded.is_done("detect")
