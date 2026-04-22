"""File-based OneNote connector (Phase 1 stub).

OneNote exports to HTML; the connector just walks a directory and pulls every
``.html``/``.htm``/``.md``/``.txt`` file. Phase 2 would pull direct from
OneNote via Graph using the source's declared notebook path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.connectors.base import Connector, ConnectorRegistry, SourceConfig, resolve_local_path
from src.models.document import DocumentMetadata, DocumentRef, RawDocument

ONENOTE_EXTENSIONS = {".html", ".htm", ".md", ".txt"}


class OneNoteConnector(Connector):
    platform = "onenote"

    def __init__(self, source: SourceConfig) -> None:
        super().__init__(source)
        self.base_dir: Path = resolve_local_path(source)

    def list_documents(self) -> list[DocumentRef]:
        refs = []
        for path in self.base_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in ONENOTE_EXTENSIONS:
                refs.append(
                    DocumentRef(
                        source_platform="onenote",
                        source_path=str(path.relative_to(self.base_dir)),
                        file_type=path.suffix.lower(),
                    )
                )
        return refs

    def fetch_document(self, ref: DocumentRef) -> RawDocument:
        file_path = self.base_dir / ref.source_path
        content = file_path.read_text(encoding="utf-8", errors="replace")

        section = file_path.parent.name if file_path.parent != self.base_dir else ""
        notebook = file_path.parent.parent.name if file_path.parent.parent != self.base_dir else ""

        metadata = DocumentMetadata(
            title=file_path.stem.replace("-", " ").replace("_", " ").title(),
            last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
            extra={
                "notebook": notebook,
                "section": section,
            },
        )

        return RawDocument(ref=ref, content=content, metadata=metadata)


ConnectorRegistry.register("onenote", OneNoteConnector)
