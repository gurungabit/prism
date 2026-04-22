"""File-based SharePoint connector (Phase 1 stub).

Phase 1 declares SharePoint sources by local path. The plan puts the proper
Microsoft Graph integration in Phase 2, at which point the source config
will carry a site URL + credentials instead of a ``path``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.connectors.base import Connector, ConnectorRegistry, SourceConfig, resolve_local_path
from src.models.document import DocumentMetadata, DocumentRef, RawDocument

SHAREPOINT_EXTENSIONS = {".docx", ".pdf", ".md", ".txt", ".html", ".htm"}


class SharePointConnector(Connector):
    platform = "sharepoint"

    def __init__(self, source: SourceConfig) -> None:
        super().__init__(source)
        self.base_dir: Path = resolve_local_path(source)

    def list_documents(self) -> list[DocumentRef]:
        refs = []
        for path in self.base_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in SHAREPOINT_EXTENSIONS:
                refs.append(
                    DocumentRef(
                        source_platform="sharepoint",
                        source_path=str(path.relative_to(self.base_dir)),
                        file_type=path.suffix.lower(),
                    )
                )
        return refs

    def fetch_document(self, ref: DocumentRef) -> RawDocument:
        file_path = self.base_dir / ref.source_path

        if file_path.suffix in {".docx", ".pdf"}:
            content = file_path.read_bytes()
        else:
            content = file_path.read_text(encoding="utf-8", errors="replace")

        folder_name = file_path.parent.name if file_path.parent != self.base_dir else ""
        metadata = DocumentMetadata(
            title=file_path.stem.replace("-", " ").replace("_", " ").title(),
            last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
            extra={"site": folder_name} if folder_name else {},
        )

        return RawDocument(ref=ref, content=content, metadata=metadata)


ConnectorRegistry.register("sharepoint", SharePointConnector)
