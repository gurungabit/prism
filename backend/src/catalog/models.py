"""Typed models for the catalog: organizations, teams, services, sources.

These are returned by repository methods and serialized straight into API
responses. Each model mirrors one row of the matching table. ``Source`` uses a
discriminated scope (``SourceScope``) to enforce that exactly one of
``org_id``, ``team_id``, ``service_id`` is populated -- same constraint as the
CHECK in ``sources``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SourceScope(str, Enum):
    ORG = "org"
    TEAM = "team"
    SERVICE = "service"


class SourceKind(str, Enum):
    GITLAB = "gitlab"
    SHAREPOINT = "sharepoint"
    EXCEL = "excel"
    ONENOTE = "onenote"


class SourceStatus(str, Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    READY = "ready"
    ERROR = "error"


class Organization(BaseModel):
    id: UUID
    name: str
    created_at: datetime


class Team(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: str = ""
    created_at: datetime


class Service(BaseModel):
    id: UUID
    team_id: UUID
    name: str
    repo_url: str = ""
    description: str = ""
    created_at: datetime


class Source(BaseModel):
    id: UUID
    org_id: UUID | None = None
    team_id: UUID | None = None
    service_id: UUID | None = None
    kind: SourceKind
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = None
    status: SourceStatus = SourceStatus.PENDING
    last_ingested_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime

    @property
    def scope(self) -> SourceScope:
        if self.org_id is not None:
            return SourceScope.ORG
        if self.team_id is not None:
            return SourceScope.TEAM
        if self.service_id is not None:
            return SourceScope.SERVICE
        raise ValueError("Source has no scope set")

    @property
    def scope_id(self) -> UUID:
        if self.org_id is not None:
            return self.org_id
        if self.team_id is not None:
            return self.team_id
        if self.service_id is not None:
            return self.service_id
        raise ValueError("Source has no scope id set")


class SourceCreate(BaseModel):
    """Payload for creating a source.

    Scope is expressed as a discriminator + id. The repository resolves it to
    one of the three nullable foreign keys on ``sources`` (and rejects multi-
    scope or zero-scope input before it hits the CHECK constraint).
    """

    scope: SourceScope
    scope_id: UUID
    kind: SourceKind
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None  # Plaintext PAT; written to source_secrets


class SourceUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    token: str | None = None  # None = leave existing secret alone
    status: SourceStatus | None = None
    last_error: str | None = None


# Snapshot returned to ingestion code. The raw token is materialized only at
# this boundary -- the main ``Source`` model never carries it.
class SourceWithSecret(BaseModel):
    source: Source
    token: str | None = None


# Literal used by the (unchanged) connector source_platform enum so we keep a
# single source of truth for the four connector kinds. Added here so tests and
# API code don't have to import both ``SourceKind`` and the literal.
ConnectorPlatform = Literal["gitlab", "sharepoint", "excel", "onenote"]
