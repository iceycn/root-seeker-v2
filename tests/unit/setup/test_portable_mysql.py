from scripts.setup.portable_mysql import resolve_mysql_download


def test_resolve_urls_differ_by_platform() -> None:
    win, _ = resolve_mysql_download("windows", "amd64")
    lin, _ = resolve_mysql_download("linux", "amd64")
    mac, _ = resolve_mysql_download("darwin", "arm64")
    assert "win" in win.lower() or "windows" in win.lower() or "winx64" in win.lower()
    assert win != lin
    assert lin != mac
    assert "8.0.40" in win
