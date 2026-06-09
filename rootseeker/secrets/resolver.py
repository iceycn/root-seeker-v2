from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rootseeker.infra_core.secret_ref import SecretRef, SecretRefKind

__all__ = ["resolve_secret"]


def resolve_secret(ref: SecretRef, *, workspace_root: Path | None = None, timeout_seconds: float = 3.0) -> str:
    if ref.kind == SecretRefKind.ENV:
        value = os.getenv(ref.ref)
        if value is None:
            raise ValueError(f"env secret not found: {ref.ref}")
        return value
    if ref.kind == SecretRefKind.FILE:
        path = Path(ref.ref)
        if not path.is_absolute() and workspace_root is not None:
            path = workspace_root / path
        if not path.exists():
            raise ValueError(f"file secret not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    if ref.kind == SecretRefKind.EXEC:
        result = subprocess.run(
            ref.ref,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(f"exec secret failed: {result.stderr.strip()}")
        return result.stdout.strip()
    raise ValueError(f"unsupported secret ref kind: {ref.kind}")
