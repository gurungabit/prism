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

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.models.document import DocumentRef, RawDocument


class LocalPathRejected(ValueError):
    """Raised when a file-based connector's path is unsafe to walk.

    Distinct from a generic ``ValueError`` so route + pipeline error
    handling can map it to a clear 400 / source-error state instead of
    a 500. Routes catch this when validating or creating sources;
    ingest catches it at connector construction.
    """


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

    Two rounds of hardening here, both flagged by codex:

    1. **Reject missing ``path``** instead of falling back to ``.``.
       The previous fallback meant a caller with API access (and we
       have no auth yet) could create a path-based source with no
       config at all and have ingest walk the backend's working
       directory -- including ``.env``, secret stores, and
       ``backend/src``.

    2. **Constrain the resolved path to ``PRISM_LOCAL_SOURCE_ROOT``**
       when the env var is set. With it set to ``/data/prism``, any
       ``config.path`` outside that subtree (or one that escapes via
       ``..`` / a symlink) is rejected. With it unset, only the
       missing-path bug is caught; the operator opts into the full
       jail by setting the env var. We keep that opt-in because
       local dev runs against ``./data`` from the repo and
       requiring the env var would break the existing test fixtures.

    Symlinks are resolved via ``Path.resolve(strict=False)``, so a
    symlink pointing outside the root fails the boundary check just
    like a literal path outside the root would.
    """

    raw_path = source.config.get("path")
    if not raw_path or not isinstance(raw_path, str) or not raw_path.strip():
        raise LocalPathRejected(
            f"Missing 'path' in {source.kind} source config. "
            "File-based connectors require an explicit path."
        )

    requested = Path(raw_path).expanduser().resolve()

    root_env = os.environ.get("PRISM_LOCAL_SOURCE_ROOT", "").strip()
    if root_env:
        root = Path(root_env).expanduser().resolve()
        try:
            requested.relative_to(root)
        except ValueError as e:
            raise LocalPathRejected(
                f"path '{raw_path}' resolves outside PRISM_LOCAL_SOURCE_ROOT "
                f"({root}). File-based sources are confined to that subtree."
            ) from e

    return requested
