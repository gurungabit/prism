from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DocumentRef(BaseModel):
    source_platform: Literal["gitlab", "gitlab_api", "sharepoint", "excel", "onenote"]
    source_path: str
    file_type: str = ""


class DocumentMetadata(BaseModel):
    title: str = ""
    author: str = ""
    last_modified: datetime | None = None
    source_url: str = ""
    labels: list[str] = []
    extra: dict = {}


class RawDocument(BaseModel):
    ref: DocumentRef
    content: bytes | str
    metadata: DocumentMetadata = DocumentMetadata()


class DocumentRegistryEntry(BaseModel):
    document_id: str
    source_platform: str
    source_path: str
    content_hash: str
    last_ingested_at: datetime | None = None
    chunk_count: int = 0
    status: Literal["pending", "indexed", "failed", "deleted"] = "pending"
