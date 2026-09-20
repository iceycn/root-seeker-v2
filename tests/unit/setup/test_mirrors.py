import os

from scripts.setup.mirrors import (
    ACR_NAMESPACE,
    ACR_REGISTRY,
    apply_cn_docker_env,
    is_cn_region,
    mysql_image_refs,
    prebuilt_candidates,
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


def test_prebuilt_candidates_cn_puts_acr_first(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    refs = prebuilt_candidates("app", hub_user="wuhun0301", tag="latest")
    assert refs[0] == f"{ACR_REGISTRY}/{ACR_NAMESPACE}/root-seeker:latest"
    assert any("daocloud" in r and "wuhun0301/rootseeker-v2" in r for r in refs)


def test_prebuilt_candidates_global_has_no_acr(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "global")
    refs = prebuilt_candidates("zoekt", hub_user="wuhun0301", tag="latest")
    assert all(ACR_REGISTRY not in r for r in refs)
    assert refs[0] == "docker.io/wuhun0301/rootseeker-v2-zoekt:latest"


def test_apply_cn_docker_env_sets_acr_compose_images(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_SETUP_REGION", "cn")
    monkeypatch.setattr("scripts.setup.mirrors.ensure_local_image", lambda *_a, **_k: True)
    env = apply_cn_docker_env({"DOCKERHUB_USER": "wuhun0301", "IMAGE_TAG": "latest"})
    assert env["APP_IMAGE"] == f"{ACR_REGISTRY}/{ACR_NAMESPACE}/root-seeker"
    assert env["ZOEKT_IMAGE"].endswith("/root-seeker-zoekt")
    assert env["GITNEXUS_IMAGE"].endswith("/root-seeker-gitnexus")
