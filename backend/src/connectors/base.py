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

from src.config import settings
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

    Three layers of hardening, all flagged by codex across rounds 10
    and 11:

    1. **Reject missing ``path``** instead of falling back to ``.``.
       The previous fallback meant a caller with API access (and we
       have no auth yet) could create a path-based source with no
       config at all and have ingest walk the backend's working
       directory -- including ``.env``, secret stores, and
       ``backend/src``.

    2. **Constrain the resolved path to the local-source jail**
       (``settings.local_source_root``, default ``./data``). Anything
       outside that subtree -- via ``..`` traversal, a symlink, or a
       literal path -- is rejected. Symlinks are resolved via
       ``Path.resolve``, so a link inside the root pointing to
       ``/etc`` fails the boundary check the same as a literal
       ``/etc`` would.

       Round 10 made this opt-in via a raw env var that nothing in
       the documented compose / settings actually set, so the default
       deployment was still vulnerable. Round 11 makes it
       default-on: ``settings.local_source_root`` is read every call,
       and the explicit escape hatch is
       ``settings.allow_unsandboxed_local_sources`` (env:
       ``PRISM_ALLOW_UNSANDBOXED_LOCAL_SOURCES``). The escape hatch
       exists so dev workflows that need a one-off directory outside
       the jail aren't permanently blocked, but it's a deliberate
       opt-in and shouldn't be set in production.
    """

    raw_path = source.config.get("path")
    if not raw_path or not isinstance(raw_path, str) or not raw_path.strip():
        raise LocalPathRejected(
            f"Missing 'path' in {source.kind} source config. "
            "File-based connectors require an explicit path."
        )

    requested = Path(raw_path).expanduser().resolve()

    if settings.allow_unsandboxed_local_sources:
        # Operator deliberately opted out of the jail. Still resolve
        # + reject missing-path above so the worst behavior (walking
        # the CWD) is impossible even with the escape hatch.
        return requested

    root_value = settings.local_source_root.strip()
    if not root_value:
        # Treat empty string as "no jail" but log loudly via a clear
        # error if anything is wrong with the config -- this should
        # never be empty in a real deployment.
        raise LocalPathRejected(
            "settings.local_source_root is empty; refuse to walk an "
            "unconstrained path. Set PRISM_LOCAL_SOURCE_ROOT or "
            "PRISM_ALLOW_UNSANDBOXED_LOCAL_SOURCES=true."
        )

    root = Path(root_value).expanduser().resolve()
    try:
        requested.relative_to(root)
    except ValueError as e:
        raise LocalPathRejected(
            f"path '{raw_path}' resolves outside local_source_root "
            f"({root}). File-based sources are confined to that subtree; "
            f"set PRISM_ALLOW_UNSANDBOXED_LOCAL_SOURCES=true to bypass "
            f"for development."
        ) from e

    return requested
