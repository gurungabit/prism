from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    source_platform: Literal["gitlab", "sharepoint", "excel", "onenote"]
    source_path: str
    source_url: str = ""
    document_title: str
    section_heading: str = ""
    team_hint: str = ""
    service_hint: str = ""
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
