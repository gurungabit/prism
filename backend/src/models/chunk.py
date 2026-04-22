from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    source_platform: Literal["gitlab", "sharepoint", "excel", "onenote"]
    source_path: str
    source_url: str = ""
    document_title: str
    section_heading: str = ""
    # ``team_hint`` / ``service_hint`` are held over from the regex era: they
    # were text pulled from paths or doc text. In Phase 1 the authoritative
    # link is the UUID below; the *_hint strings remain for backwards compat
    # with existing search filters and any chunks indexed pre-migration.
    team_hint: str = ""
    service_hint: str = ""
    # Declared scope pointers. Exactly the shape stored in ``kg_documents``.
    # ``org_id`` is always set for chunks ingested under the declared model;
    # the others track the narrowest scope the source was attached to.
    org_id: UUID | None = None
    team_id: UUID | None = None
    service_id: UUID | None = None
    doc_type: Literal[
        "wiki",
        "issue",
        "readme",
        "spreadsheet",
        "meeting_notes",
        "runbook",
        "merge_request",
        "incident_report",
        "service_catalog",
        "architecture_doc",
        "unknown",
    ] = "unknown"
    last_modified: datetime | None = None
    author: str = ""
    chunk_index: int = 0
    total_chunks: int = 1


class Chunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: "")
    document_id: str = ""
    content: str
    embedding: list[float] = Field(default_factory=list)
    metadata: ChunkMetadata
    canonical_chunk_id: str | None = None
    score: float = 0.0
