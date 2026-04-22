"""Base types for connectors.

Connectors used to be instantiated per local directory ("give me everything
under ``data/sources/gitlab``"). In the declared model they're instantiated
per *declared source* -- a row in the ``sources`` table -- and receive a
``SourceConfig`` describing what to fetch (a GitLab group, a single project,
a local path, etc.).

For Phase 1 only the GitLab connector has the full API-based rewrite. The
file-based connectors (SharePoint / Excel / OneNote) accept the same
``SourceConfig`` shape but read from ``config.path`` on the local filesystem,
so the pipeline can treat every connector uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.models.document import DocumentRef, RawDocument


@dataclass
class SourceConfig:
    """Runtime config for a single connector invocation.

    ``config`` mirrors the ``sources.config`` JSONB column: connector-specific
    keys (e.g. ``group_path``, ``project_path``, ``path``). ``token`` carries
    the decrypted/loaded secret when one is needed (GitLab PAT). Keeping them
    separate from the stored model lets the pipeline materialize the token
    only at the boundary of the connector call.
    """

    kind: str
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    token: str | None = None


class Connector(ABC):
    """Abstract connector.

    Subclasses accept a ``SourceConfig`` and expose ``list_documents`` +
    ``fetch_document``. The pipeline iterates ``list_documents``, turns each
    ``DocumentRef`` into a chunk set, and tags every chunk with the source's
    scope.
    """

    platform: str

    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    @abstractmethod
    def list_documents(self) -> list[DocumentRef]: ...

    @abstractmethod
    def fetch_document(self, ref: DocumentRef) -> RawDocument: ...

    async def aclose(self) -> None:
        """Optional async cleanup. Default is a no-op."""


class ConnectorRegistry:
    """Maps a connector ``kind`` string to its implementing class.

    Every declared source has a ``kind`` (``"gitlab"``, ``"sharepoint"``, …)
    that this registry turns into a live connector. Phase 1 wires up only
    GitLab for live API fetch; the others remain path-based stubs.
    """

    _connectors: dict[str, type[Connector]] = {}

    @classmethod
    def register(cls, platform: str, connector_class: type[Connector]) -> None:
        cls._connectors[platform] = connector_class

    @classmethod
    def get(cls, platform: str) -> type[Connector] | None:
        return cls._connectors.get(platform)

    @classmethod
    def all_platforms(cls) -> list[str]:
        return list(cls._connectors.keys())

    @classmethod
    def create(cls, source: SourceConfig) -> Connector:
        connector_cls = cls.get(source.kind)
        if connector_cls is None:
            raise ValueError(f"Unknown connector kind: {source.kind}")
        return connector_cls(source)


# ---------- Shared helper for local filesystem connectors ----------


def resolve_local_path(source: SourceConfig) -> Path:
    """Return the on-disk directory a path-based connector should walk.

    Looks at ``source.config['path']`` first, falling back to the legacy
    ``data/sources/{kind}`` convention if the source has no explicit path.
    """

    raw_path = source.config.get("path")
    if raw_path:
        return Path(raw_path).expanduser().resolve()

    # Fallback for dev-time sources that were declared without a path. Keeps
    # the file-based test fixtures working without forcing every SourceConfig
    # to carry a path.
    return Path(source.config.get("base_dir", ".")).expanduser().resolve()
