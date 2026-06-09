from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel

__all__ = ["SecretRefKind", "SecretRef"]


class SecretRefKind(StrEnum):
    ENV = "env"
    FILE = "file"
    EXEC = "exec"


class SecretRef(RootSeekerModel):
    kind: SecretRefKind
    ref: str = Field(min_length=1, description="Env var name or file path token")
