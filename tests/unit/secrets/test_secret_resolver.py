from pathlib import Path

import pytest

from rootseeker.infra_core import SecretRef, SecretRefKind
from rootseeker.secrets import resolve_secret


def test_secret_resolver_env_and_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_TEST_SECRET", "env-value")
    env_value = resolve_secret(SecretRef(kind=SecretRefKind.ENV, ref="ROOTSEEKER_TEST_SECRET"))
    assert env_value == "env-value"

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-value\n", encoding="utf-8")
    file_value = resolve_secret(
        SecretRef(kind=SecretRefKind.FILE, ref=str(secret_file)),
        workspace_root=tmp_path,
    )
    assert file_value == "file-value"


def test_secret_resolver_exec() -> None:
    value = resolve_secret(SecretRef(kind=SecretRefKind.EXEC, ref="echo exec-value"))
    assert value == "exec-value"
