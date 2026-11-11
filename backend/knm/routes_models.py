# KNM FORK ONLY - NEVER SEND UPSTREAM
"""Request bodies shared by the person-facing and admin routes."""

from pydantic import BaseModel, Field


class DownloadRequest(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=300)
    year: int | None = None
    tmdb_id: int | str | None = None


class AllowEntry(BaseModel):
    server_id: int
    user_id: int
    username: str | None = None
    allowed: bool = True
    daily_cap: int | None = Field(default=None, ge=0, le=1000)


class AllowlistUpdate(BaseModel):
    default_cap: int | None = Field(default=None, ge=0, le=1000)
    entries: list[AllowEntry] = []


class AckRequest(BaseModel):
    ids: list[int]
