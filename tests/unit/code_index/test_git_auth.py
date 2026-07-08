import pytest

from rootseeker.code_index.git_auth import build_authenticated_git_url, mask_git_url


def test_build_authenticated_git_url_github() -> None:
    url = build_authenticated_git_url(
        "https://github.com/org/repo.git",
        provider="github",
        username="",
        token="gh-token",
    )
    assert url.startswith("https://x-access-token:gh-token@github.com/")


def test_build_authenticated_git_url_yunxiao_requires_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROOTSEEKER_CODEUP_GIT_USERNAME", raising=False)
    with pytest.raises(ValueError, match="云效 Codeup 缺少 HTTPS 克隆账号"):
        build_authenticated_git_url(
            "https://codeup.aliyun.com/org/repo.git",
            provider="yunxiao",
            username="",
            token="pt-token",
        )


def test_build_authenticated_git_url_yunxiao_with_username() -> None:
    url = build_authenticated_git_url(
        "https://codeup.aliyun.com/org/repo.git",
        provider="yunxiao",
        username="clone-user",
        token="pt-token",
    )
    assert url == "https://clone-user:pt-token@codeup.aliyun.com/org/repo.git"


def test_mask_git_url() -> None:
    masked = mask_git_url("https://user:secret@codeup.aliyun.com/org/repo.git")
    assert masked == "https://***:***@codeup.aliyun.com/org/repo.git"
