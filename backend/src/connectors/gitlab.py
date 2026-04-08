from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.connectors.base import Connector, ConnectorRegistry
from src.models.document import DocumentMetadata, DocumentRef, RawDocument

GITLAB_EXTENSIONS = {".md", ".txt", ".py", ".js", ".ts", ".yaml", ".yml", ".json", ".rst"}


class GitLabConnector(Connector):
    platform = "gitlab"

    def list_documents(self) -> list[DocumentRef]:
        refs = []
        for path in self.base_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in GITLAB_EXTENSIONS or path.name.lower() in {"readme", "changelog"}:
                refs.append(
                    DocumentRef(
                        source_platform="gitlab",
                        source_path=str(path.relative_to(self.base_dir)),
                        file_type=path.suffix.lower() or ".txt",
                    )
                )
        return refs

    def fetch_document(self, ref: DocumentRef) -> RawDocument:
        file_path = self.base_dir / ref.source_path
        content = file_path.read_text(encoding="utf-8", errors="replace")

        metadata = DocumentMetadata(
            title=_extract_title(file_path, content),
            last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
        )

        if file_path.suffix == ".json":
            try:
                data = json.loads(content)
                metadata.title = data.get("title", metadata.title)
                metadata.author = data.get("author", {}).get("name", "")
                metadata.labels = data.get("labels", [])
            except json.JSONDecodeError:
                pass

        return RawDocument(ref=ref, content=content, metadata=metadata)


def _extract_title(path: Path, content: str) -> str:
    if path.suffix == ".md":
        for line in content.split("\n")[:5]:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


ConnectorRegistry.register("gitlab", GitLabConnector)
