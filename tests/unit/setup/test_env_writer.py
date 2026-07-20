from pathlib import Path

from scripts.setup.env_writer import merge_env_file


def test_merge_preserves_existing_secret(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("ROOTSEEKER_LLM_API_KEY=keep-me\nFOO=1\n", encoding="utf-8")
    merge_env_file(
        path,
        {"FOO": "2", "ROOTSEEKER_LLM_API_KEY": "new"},
        overwrite_existing=False,
    )
    text = path.read_text(encoding="utf-8")
    assert "ROOTSEEKER_LLM_API_KEY=keep-me" in text
    assert "FOO=2" in text


def test_merge_overwrite_when_requested(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("FOO=1\n", encoding="utf-8")
    merge_env_file(path, {"FOO": "2"}, overwrite_existing=True)
    assert "FOO=2" in path.read_text(encoding="utf-8")
