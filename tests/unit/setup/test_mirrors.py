import os

from scripts.setup.mirrors import (
    is_cn_region,
    mysql_image_refs,
    rewrite_mysql_archive_url,
    setup_region,
)


def test_default_region_global(monkeypatch) -> None:
    monkeypatch.delenv("ROOTSEEKER_SETUP_REGION", raising=False)
    assert setup_region() == "global"
    assert is_cn_region() is False


def test_cn_region_aliases(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    assert setup_region() == "cn"
    assert is_cn_region() is True
    refs = mysql_image_refs()
    assert any("daocloud" in r for r in refs)
    assert "mysql:8.0" in refs


def test_rewrite_mysql_url_cn(monkeypatch) -> None:
    official = "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-8.0.40-winx64.zip"
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "global")
    assert rewrite_mysql_archive_url(official) == official
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    rewritten = rewrite_mysql_archive_url(official)
    assert "tuna.tsinghua.edu.cn" in rewritten
    assert rewritten.endswith("MySQL-8.0/mysql-8.0.40-winx64.zip")
