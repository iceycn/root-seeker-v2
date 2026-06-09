from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RootSeekerModel",
    "EntityRef",
    "Page",
    "PagedResult",
    "SortSpec",
    "utc_now",
    "new_id",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str = "") -> str:
    uid = str(uuid.uuid4())
    return f"{prefix}{uid}" if prefix else uid


class RootSeekerModel(BaseModel):
    """Shared base for contracts: consistent validation and no surprise fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class EntityRef(RootSeekerModel):
    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)


class Page(RootSeekerModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class PagedResult(RootSeekerModel):
    """Generic list envelope for registry/API style responses (items are domain-specific)."""

    items: list[Any] = Field(default_factory=list)
    total: int = Field(ge=0)
    page: Page = Field(default_factory=Page)


SortDirection = Literal["asc", "desc"]


class SortSpec(RootSeekerModel):
    field: str = Field(min_length=1)
    direction: SortDirection = "asc"
