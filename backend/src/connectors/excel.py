"""File-based Excel connector (Phase 1 stub).

Reads ``.xlsx``/``.xls``/``.csv`` files under a path declared in the source
config. The plan's Phase 2 pulls these from SharePoint / OneDrive via Graph.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.connectors.base import Connector, ConnectorRegistry, SourceConfig, resolve_local_path
from src.models.document import DocumentMetadata, DocumentRef, RawDocument

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".csv"}


class ExcelConnector(Connector):
    platform = "excel"

    def __init__(self, source: SourceConfig) -> None:
        super().__init__(source)
        self.base_dir: Path = resolve_local_path(source)

    def list_documents(self) -> list[DocumentRef]:
        refs = []
        for path in self.base_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in EXCEL_EXTENSIONS:
                refs.append(
                    DocumentRef(
                        source_platform="excel",
                        source_path=str(path.relative_to(self.base_dir)),
                        file_type=path.suffix.lower(),
                    )
                )
        return refs

    def fetch_document(self, ref: DocumentRef) -> RawDocument:
        file_path = self.base_dir / ref.source_path
        content = file_path.read_bytes()

        metadata = DocumentMetadata(
            title=file_path.stem.replace("-", " ").replace("_", " ").title(),
            last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
            extra={"sheets": []},
        )

        return RawDocument(ref=ref, content=content, metadata=metadata)


ConnectorRegistry.register("excel", ExcelConnector)
