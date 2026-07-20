from pathlib import Path

from scripts.setup.indexers import setup_indexers
from scripts.setup.native_path import configure_sqlite
from scripts.setup.state import SetupState


def test_configure_sqlite_writes_env(tmp_path: Path) -> None:
    configure_sqlite(tmp_path)
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ROOTSEEKER_STORAGE_BACKEND=sqlite" in text


def test_indexers_zoekt_ok_when_bins_exist(tmp_path: Path) -> None:
    bin_dir = tmp_path / "docker" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "zoekt-index").write_text("", encoding="utf-8")
    (bin_dir / "zoekt-webserver").write_text("", encoding="utf-8")
    summary = setup_indexers(tmp_path, SetupState(), noninteractive=True)
    assert summary["zoekt"].startswith("ok")
