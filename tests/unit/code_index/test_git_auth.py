import pytest

from rootseeker.code_index.git_auth import (
    assert_git_url_allowed_for_provider,
    build_authenticated_git_url,
    git_url_host_allowed,
    mask_git_url,
    sanitize_git_error_message,
)


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


def test_sanitize_git_error_message_masks_embedded_credentials() -> None:
    raw = (
        "fatal: unable to access 'https://clone-user:pt-token@codeup.aliyun.com/org/repo.git/': "
        "The requested URL returned error: 403"
    )
    sanitized = sanitize_git_error_message(raw)
    assert "pt-token" not in sanitized
    assert "clone-user" not in sanitized
    assert "***:***@codeup.aliyun.com" in sanitized


def test_git_url_host_allowed_for_provider() -> None:
    assert git_url_host_allowed("https://github.com/org/repo.git", "github")
    assert git_url_host_allowed("https://codeup.aliyun.com/org/repo.git", "yunxiao")
    assert not git_url_host_allowed("https://evil.example/repo.git", "github")


def test_assert_git_url_allowed_for_provider_rejects_mismatch() -> None:
    with pytest.raises(ValueError, match="不匹配"):
        assert_git_url_allowed_for_provider("https://evil.example/repo.git", "github")
