"""Declared-source ingestion pipeline.

The entry point is now ``ingest_source(source_id, force=False)``. Given a
declared source:

1. Resolve it to a ``SourceConfig`` + loaded token.
2. Instantiate the matching connector from the registry.
3. Walk ``list_documents()``; for each ref, fetch + parse + chunk.
4. Stamp every chunk with the source's scope ``(org_id, team_id, service_id)``.
5. Embed, index into OpenSearch (with ``source_id`` so we can delete-by-source),
   and write ``kg_documents`` rows carrying the same scope.

Service-to-service dependencies are user-managed via the UI -- we don't
try to extract them from text anymore (the LLM pass was noisy and the
regex pass was hand-wavy).

Status transitions on ``sources``: pending -> syncing -> ready | error.
``last_ingested_at`` only moves forward on a successful run.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.catalog import (
    OrgRepository,
    ServiceRepository,
    SourceRepository,
    SourceStatus,
    TeamRepository,
)
from src.catalog.models import Source
from src.config import settings
from src.connectors.base import ConnectorRegistry, SourceConfig
from src.ingestion.chunker import chunk_document
from src.ingestion.deduplicator import ChunkDeduplicator
from src.ingestion.embedder import embed_chunks
from src.ingestion.indexer import (
    delete_by_document_id,
    delete_by_source_id,
    get_opensearch_client,
    index_chunks,
    setup_index,
)
from src.ingestion.knowledge_store import KnowledgeStore
from src.ingestion.parser import parse_document
from src.ingestion.registry import DocumentRegistry, compute_content_hash
from src.ingestion.summarizer import attach_summary_chunks
from src.models.chunk import Chunk
from src.models.document import DocumentRef, RawDocument
from src.observability.logging import get_logger

log = get_logger("pipeline")


@dataclass
class PreparedDocument:
    document_id: str
    raw_doc: RawDocument
    parsed_content: str
    content_hash: str
    chunks: list[Chunk] = field(default_factory=list)
    # When the doc replaces an earlier ingest of the same source_path
    # (hash mismatch), this carries the previous ``document_id``. The
    # graph table's ``ON CONFLICT (id)`` upsert can't reach that row
    # because the new id is freshly generated, so phase 4 explicitly
    # deletes it after the new row + registry upsert succeed.
    replaces_document_id: str | None = None


@dataclass
class SourceScope:
    """Materialized scope resolved from a declared source.

    ``org_id`` is always set (a source is always anchored in an org, even a
    service-scoped one, via team_id -> services.team_id -> teams.org_id).
    ``team_id`` and ``service_id`` track the narrowest scope.
    """

    org_id: UUID
    team_id: UUID | None = None
    service_id: UUID | None = None


class IngestionPipeline:
    def __init__(
        self,
        registry: DocumentRegistry,
        store: KnowledgeStore,
        org_repo: OrgRepository,
        team_repo: TeamRepository,
        service_repo: ServiceRepository,
        source_repo: SourceRepository,
        deduplicator: ChunkDeduplicator | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.org_repo = org_repo
        self.team_repo = team_repo
        self.service_repo = service_repo
        self.source_repo = source_repo
        self.deduplicator = deduplicator or ChunkDeduplicator()
        self.os_client = get_opensearch_client()

    @classmethod
    async def create(cls) -> IngestionPipeline:
        # Catalog repos share the schema bootstrap; creating any of them
        # guarantees the catalog tables exist. We create each explicitly so
        # the pipeline has concrete references for the rest of the run.
        registry = await DocumentRegistry.create()
        store = await KnowledgeStore.create()
        org_repo = await OrgRepository.create()
        team_repo = await TeamRepository.create()
        service_repo = await ServiceRepository.create()
        source_repo = await SourceRepository.create()
        pipeline = cls(registry, store, org_repo, team_repo, service_repo, source_repo)
        setup_index(pipeline.os_client)
        return pipeline

    # ----- entry points -----

    async def ingest_source(self, source_id: UUID, *, force: bool = False) -> dict[str, Any]:
        """Ingest a single declared source.

        ``force=True`` wipes the source's existing chunks + registry rows
        before re-ingesting. Without it, documents with unchanged content
        hashes are skipped.
        """
        with_secret = await self.source_repo.get_with_secret(source_id)
        if with_secret is None:
            raise ValueError(f"Unknown source: {source_id}")

        source = with_secret.source
        scope = await self._resolve_scope(source)
        source_config = SourceConfig(
            kind=source.kind.value,
            name=source.name,
            config=dict(source.config),
            token=with_secret.token,
        )

        connector_cls = ConnectorRegistry.get(source_config.kind)
        if connector_cls is None:
            await self.source_repo.mark_status(
                source_id,
                SourceStatus.ERROR,
                last_error=f"No connector registered for kind '{source_config.kind}'",
            )
            raise ValueError(f"No connector registered for kind '{source_config.kind}'")

        await self.source_repo.mark_status(source_id, SourceStatus.SYNCING, last_error=None)
        try:
            await self.source_repo.begin_ingest_progress(source_id, phase="starting")
        except Exception as progress_err:
            log.warning(
                "ingest_progress_begin_failed",
                source_id=str(source_id),
                error=str(progress_err)[:200],
            )

        if force:
            try:
                await self.source_repo.update_ingest_progress(
                    source_id,
                    phase="clearing",
                    total_documents=0,
                    processed_documents=0,
                    indexed_documents=0,
                    skipped_documents=0,
                    failed_documents=0,
                )
            except Exception as progress_err:
                log.warning(
                    "ingest_progress_update_failed",
                    source_id=str(source_id),
                    phase="clearing",
                    error=str(progress_err)[:200],
                )
            delete_by_source_id(source_id, self.os_client)

        connector = connector_cls(source_config)
        try:
            stats = await self._ingest_with_connector(connector, source, scope, force=force)
        except Exception as e:  # noqa: BLE001
            log.error("ingest_source_failed", source_id=str(source_id), error=str(e))
            await self.source_repo.mark_status(
                source_id,
                SourceStatus.ERROR,
                last_error=str(e)[:500],
            )
            try:
                await self.source_repo.finish_ingest_progress(source_id, phase="failed")
            except Exception as progress_err:
                log.warning(
                    "ingest_progress_finish_failed",
                    source_id=str(source_id),
                    phase="failed",
                    error=str(progress_err)[:200],
                )
            raise
        finally:
            await connector.aclose()

        # Partial failures keep any successful chunks but surface an error
        # status so the operator knows exactly which documents broke.
        failed_count = int(stats.get("failed", 0) or 0)
        index_errors = int(stats.get("index_errors", 0) or 0)
        tombstone_pending = int(stats.get("tombstone_retry_pending", 0) or 0)
        failures = stats.get("failures") or []
        if failed_count or index_errors or tombstone_pending:
            parts: list[str] = []
            if failed_count:
                parts.append(f"{failed_count} document(s) failed to parse/index")
            if index_errors:
                parts.append(f"{index_errors} OpenSearch bulk error(s)")
            if tombstone_pending:
                parts.append(
                    f"{tombstone_pending} stale document cleanup(s) pending retry"
                )
            # Inline the actual failing paths + reasons so the operator
            # can fix them without grepping logs. Cap at the first three
            # so a many-doc failure doesn't blow past the 500-char limit.
            for entry in failures[:3]:
                parts.append(f"{entry['path']}: {entry['reason']}")
            if len(failures) > 3:
                parts.append(f"(+{len(failures) - 3} more)")
            first_err = stats.get("index_first_error")
            if first_err and not failures:
                parts.append(f"first: {first_err}")
            await self.source_repo.mark_status(
                source_id,
                SourceStatus.ERROR,
                last_error="; ".join(parts)[:500],
                last_ingested_at=datetime.now(tz=timezone.utc),
            )
            await self._finish_progress(source_id, stats, phase="failed")
        else:
            await self.source_repo.mark_status(
                source_id,
                SourceStatus.READY,
                last_error=None,
                last_ingested_at=datetime.now(tz=timezone.utc),
            )
            await self._finish_progress(source_id, stats, phase="complete")
        stats["source_id"] = str(source_id)
        return stats

    # ----- internals -----

    async def _resolve_scope(self, source: Source) -> SourceScope:
        """Fill in the implicit org/team ids for team-scoped and service-scoped sources."""
        if source.org_id is not None:
            return SourceScope(org_id=source.org_id)

        if source.team_id is not None:
            team = await self.team_repo.get(source.team_id)
            if team is None:
                raise ValueError(f"Team {source.team_id} referenced by source {source.id} not found")
            return SourceScope(org_id=team.org_id, team_id=team.id)

        if source.service_id is not None:
            service = await self.service_repo.get(source.service_id)
            if service is None:
                raise ValueError(f"Service {source.service_id} referenced by source {source.id} not found")
            team = await self.team_repo.get(service.team_id)
            if team is None:
                raise ValueError(f"Team {service.team_id} for service {service.id} not found")
            return SourceScope(org_id=team.org_id, team_id=team.id, service_id=service.id)

        raise ValueError(f"Source {source.id} has no scope set")

    async def _record_progress(
        self,
        source: Source,
        stats: dict[str, Any],
        *,
        phase: str,
        current_path: str | None = None,
    ) -> None:
        try:
            await self.source_repo.update_ingest_progress(
                source.id,
                phase=phase,
                total_documents=int(stats.get("total", 0) or 0),
                processed_documents=int(stats.get("processed", 0) or 0),
                indexed_documents=int(stats.get("indexed", 0) or 0),
                skipped_documents=int(stats.get("skipped", 0) or 0),
                failed_documents=int(stats.get("failed", 0) or 0),
                current_path=current_path,
            )
        except Exception as e:
            log.warning(
                "ingest_progress_update_failed",
                source_id=str(source.id),
                phase=phase,
                error=str(e)[:200],
            )

    async def _finish_progress(
        self,
        source_id: UUID,
        stats: dict[str, Any],
        *,
        phase: str,
    ) -> None:
        try:
            source = await self.source_repo.get(source_id)
            if source is not None:
                await self._record_progress(source, stats, phase=phase)
            await self.source_repo.finish_ingest_progress(source_id, phase=phase)
        except Exception as e:
            log.warning(
                "ingest_progress_finish_failed",
                source_id=str(source_id),
                phase=phase,
                error=str(e)[:200],
            )

    async def _ingest_with_connector(
        self,
        connector,
        source: Source,
        scope: SourceScope,
        *,
        force: bool,
    ) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "total": 0,
            "processed": 0,
            "indexed": 0,
            "skipped": 0,
            "failed": 0,
            "skipped_empty": 0,
            # Each entry: {"path": str, "reason": str}. Surfaced in
            # source.last_error so the operator sees exactly which doc
            # broke and why.
            "failures": [],
        }

        try:
            await self._record_progress(source, stats, phase="listing")
            # Connectors are sync httpx today (GitLab pages projects + tree
            # walks via blocking calls); push the listing into a worker
            # thread so the event loop keeps serving API requests during
            # the initial fan-out on a large group.
            doc_refs = await asyncio.to_thread(connector.list_documents)
        except Exception as e:  # noqa: BLE001
            log.error("list_documents_failed", source=source.name, error=str(e))
            raise

        log.info("documents_found", source=source.name, count=len(doc_refs))
        stats["total"] = len(doc_refs)
        await self._record_progress(source, stats, phase="fetching")

        # Tombstone phase runs FIRST -- before any parse/embed/index work --
        # so paths missing from the upstream listing get cleaned up even
        # when every doc this run is a skip (unchanged content) or every
        # doc fails to parse. Without this, removing a doc upstream would
        # leave its chunks searchable until something forced a fresh
        # re-index of the source.
        await self._tombstone_removed_docs(source, doc_refs, stats)

        prepared: list[PreparedDocument] = []

        log.info("phase_1_parse_chunk", source=source.name, total=len(doc_refs))
        for idx, ref in enumerate(doc_refs, start=1):
            try:
                await self._record_progress(
                    source, stats, phase="fetching", current_path=ref.source_path
                )
                log.info(
                    "fetch_document_start",
                    source=source.name,
                    index=idx,
                    total=len(doc_refs),
                    path=ref.source_path,
                )
                raw_doc = await self._fetch_with_retry(connector, ref, idx)
                log.info(
                    "fetch_document_ok",
                    source=source.name,
                    index=idx,
                    path=ref.source_path,
                )
                content = raw_doc.content if isinstance(raw_doc.content, str) else raw_doc.content
                content_hash = compute_content_hash(content)

                replaces_document_id: str | None = None
                if not force:
                    log.info(
                        "registry_lookup_start",
                        source=source.name,
                        index=idx,
                        path=ref.source_path,
                    )
                    existing = await self.registry.get_by_path(
                        ref.source_path, source_id=source.id
                    )
                    log.info(
                        "registry_lookup_ok",
                        source=source.name,
                        index=idx,
                        existed=bool(existing),
                    )
                    if existing and existing["content_hash"] == content_hash:
                        stats["skipped"] += 1
                        stats["processed"] += 1
                        await self._record_progress(
                            source,
                            stats,
                            phase="fetching",
                            current_path=ref.source_path,
                        )
                        continue

                    if existing:
                        # Drop the stale OS chunk set before re-indexing.
                        # The old kg_documents row stays for now -- phase
                        # 4 deletes it after the new graph row + registry
                        # upsert land, so a crash in between leaves the
                        # registry pointing somewhere with a usable row.
                        log.info(
                            "opensearch_delete_start",
                            source=source.name,
                            index=idx,
                            document_id=existing["document_id"],
                        )
                        await asyncio.to_thread(
                            delete_by_document_id,
                            existing["document_id"],
                            self.os_client,
                        )
                        log.info(
                            "opensearch_delete_ok",
                            source=source.name,
                            index=idx,
                        )
                        replaces_document_id = existing["document_id"]

                document_id = str(uuid.uuid4())
                parsed_content = parse_document(raw_doc)
                log.info(
                    "parsed",
                    source=source.name,
                    index=idx,
                    content_len=len(parsed_content),
                )

                if not parsed_content.strip():
                    # Empty parse is NOT a failure of our system -- the
                    # file genuinely has no extractable text (binary
                    # masquerading as markdown, 0-byte placeholder,
                    # etc.). Count as skipped + log explicitly so it's
                    # not silent, but don't tank the source status.
                    stats["skipped_empty"] += 1
                    stats["skipped"] += 1
                    stats["processed"] += 1
                    log.warning(
                        "document_parse_empty_skipped",
                        source=source.name,
                        index=idx,
                        path=ref.source_path,
                    )
                    await self._record_progress(
                        source,
                        stats,
                        phase="fetching",
                        current_path=ref.source_path,
                    )
                    continue

                chunks = await asyncio.to_thread(
                    chunk_document,
                    document_id,
                    parsed_content,
                    raw_doc,
                    chunk_size_tokens=settings.chunk_size_tokens,
                    overlap_tokens=settings.chunk_overlap_tokens,
                    chunking_strategy=settings.chunking_strategy,
                    semantic_min_chunk_tokens=settings.semantic_chunk_min_tokens,
                    semantic_breakpoint_percentile=settings.semantic_chunk_breakpoint_percentile,
                    semantic_breakpoint_threshold=settings.semantic_chunk_breakpoint_threshold,
                )
                log.info(
                    "chunked",
                    source=source.name,
                    index=idx,
                    chunks=len(chunks),
                    content_len=len(parsed_content),
                )
                self._stamp_scope_onto_chunks(chunks, scope)

                log.info("dedup_start", source=source.name, index=idx, chunks=len(chunks))
                for chunk in chunks:
                    canonical = self.deduplicator.check_duplicate(chunk.chunk_id, chunk.content)
                    if canonical:
                        chunk.canonical_chunk_id = canonical
                log.info("dedup_ok", source=source.name, index=idx)

                prepared.append(
                    PreparedDocument(
                        document_id=document_id,
                        raw_doc=raw_doc,
                        parsed_content=parsed_content,
                        content_hash=content_hash,
                        chunks=chunks,
                        replaces_document_id=replaces_document_id,
                    )
                )
                stats["processed"] += 1
                await self._record_progress(
                    source,
                    stats,
                    phase="fetching",
                    current_path=ref.source_path,
                )

            except Exception as e:  # noqa: BLE001
                log.error("document_parse_failed", path=ref.source_path, error=str(e))
                stats["failed"] += 1
                stats["processed"] += 1
                stats["failures"].append(
                    {"path": ref.source_path, "reason": f"parse: {str(e)[:200]}"}
                )
                await self._record_progress(
                    source,
                    stats,
                    phase="fetching",
                    current_path=ref.source_path,
                )

        if not prepared:
            log.info("no_documents_to_index", source=source.name)
            return stats

        # Best-effort summary chunks. Re-stamp scope after attach --
        # summary chunks come back unscoped and the org_id filter on
        # retrieval would otherwise hide them.
        await self._record_progress(source, stats, phase="summarizing")
        summary_count = await attach_summary_chunks(prepared)
        if summary_count:
            for doc in prepared:
                self._stamp_scope_onto_chunks(doc.chunks, scope)
            log.info(
                "summary_chunks_attached",
                source=source.name,
                count=summary_count,
            )

        log.info("phase_2_embed", source=source.name, documents=len(prepared))
        await self._record_progress(source, stats, phase="embedding")
        all_chunks: list[Chunk] = []
        for doc in prepared:
            all_chunks.extend(doc.chunks)

        # Embedding + OpenSearch bulk index are both blocking CPU/IO.
        # Offload to a worker thread so API requests keep being served
        # while a large project is syncing.
        all_chunks = await asyncio.to_thread(
            embed_chunks, all_chunks, batch_size=256
        )
        log.info("embedding_complete", total_chunks=len(all_chunks))

        log.info("phase_3_index", source=source.name, chunks=len(all_chunks))
        await self._record_progress(source, stats, phase="indexing")
        indexed_count, index_errors = await asyncio.to_thread(
            index_chunks, all_chunks, self.os_client, source_id=source.id
        )
        log.info(
            "opensearch_indexed",
            count=indexed_count,
            error_count=len(index_errors),
        )
        # OpenSearch bulk failures used to be logged-and-forgotten while the
        # source still got marked ``ready``. Surface them in stats so the
        # caller can flip status to ``error`` or include them in
        # ``last_error``.
        if index_errors:
            stats["index_errors"] = len(index_errors)
            stats["index_first_error"] = str(index_errors[0])[:300]

        log.info("phase_4_graph", source=source.name, documents=len(prepared))
        for doc in prepared:
            try:
                await self._record_progress(
                    source,
                    stats,
                    phase="saving",
                    current_path=doc.raw_doc.ref.source_path,
                )
                await self.store.add_document(
                    doc.document_id,
                    doc.raw_doc,
                    source_id=source.id,
                    org_id=scope.org_id,
                    team_id=scope.team_id,
                    service_id=scope.service_id,
                )

                await self.registry.upsert(
                    document_id=doc.document_id,
                    source_platform=doc.raw_doc.ref.source_platform,
                    source_path=doc.raw_doc.ref.source_path,
                    content_hash=doc.content_hash,
                    chunk_count=len(doc.chunks),
                    status="indexed",
                    source_id=source.id,
                )

                stats["indexed"] += 1
                await self._record_progress(
                    source,
                    stats,
                    phase="saving",
                    current_path=doc.raw_doc.ref.source_path,
                )
            except Exception as e:  # noqa: BLE001
                log.error("graph_populate_failed", path=doc.raw_doc.ref.source_path, error=str(e))
                stats["failed"] += 1
                stats["failures"].append(
                    {
                        "path": doc.raw_doc.ref.source_path,
                        "reason": f"graph_populate: {str(e)[:200]}",
                    }
                )
                await self._record_progress(
                    source,
                    stats,
                    phase="saving",
                    current_path=doc.raw_doc.ref.source_path,
                )
                continue

            # Content-update cleanup: drop the orphaned graph row keyed
            # on the previous document_id. Runs *after* indexed += 1
            # because a failure here is a small leak, not an indexing
            # failure -- the new chunk set is already searchable.
            if (
                doc.replaces_document_id
                and doc.replaces_document_id != doc.document_id
            ):
                try:
                    await self.store.delete_documents(
                        source.id, [doc.replaces_document_id]
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "kg_documents_orphan_cleanup_failed",
                        path=doc.raw_doc.ref.source_path,
                        old_document_id=doc.replaces_document_id,
                        error=str(e)[:200],
                    )

        log.info(
            "source_complete",
            source=source.name,
            indexed=stats["indexed"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            tombstoned=stats.get("tombstoned", 0),
            tombstone_retry_pending=stats.get("tombstone_retry_pending", 0),
            index_errors=stats.get("index_errors", 0),
        )
        return stats

    async def _tombstone_removed_docs(
        self,
        source: Source,
        doc_refs: list[DocumentRef],
        stats: dict[str, Any],
    ) -> None:
        """Remove registry + graph rows whose upstream paths disappeared.

        OpenSearch cleanup runs first. Documents whose chunks cannot be
        deleted have BOTH their ``document_registry`` row AND their
        ``kg_documents`` row left in place so the next ingest can retry
        with the same document ids. Successful cleanups drop both rows
        together in a single Postgres transaction so the source's
        document footprint stays consistent.
        """
        upstream_paths = {ref.source_path for ref in doc_refs}
        existing_for_source = await self.registry.get_for_source(source.id)
        stale_rows = [
            row
            for row in existing_for_source
            if row["source_path"] not in upstream_paths
        ]
        if not stale_rows:
            return

        log.info(
            "tombstoning_removed_docs",
            source=source.name,
            count=len(stale_rows),
        )

        succeeded_doc_ids: list[str] = []
        retry_pending = 0
        for row in stale_rows:
            doc_id = row["document_id"]
            try:
                await asyncio.to_thread(
                    delete_by_document_id, doc_id, self.os_client
                )
                succeeded_doc_ids.append(doc_id)
            except Exception as e:  # noqa: BLE001
                retry_pending += 1
                log.warning(
                    "tombstone_opensearch_delete_failed_retain_registry",
                    document_id=doc_id,
                    source_path=row.get("source_path"),
                    error=str(e)[:200],
                )

        removed = (
            await self.registry.delete_by_document_ids_with_graph(
                source.id, succeeded_doc_ids
            )
            if succeeded_doc_ids
            else []
        )
        stats["tombstoned"] = len(removed)
        if retry_pending:
            stats["tombstone_retry_pending"] = retry_pending

    def _stamp_scope_onto_chunks(self, chunks: list[Chunk], scope: SourceScope) -> None:
        for chunk in chunks:
            chunk.metadata.org_id = scope.org_id
            chunk.metadata.team_id = scope.team_id
            chunk.metadata.service_id = scope.service_id

    async def _fetch_with_retry(
        self,
        connector,
        ref: DocumentRef,
        idx: int,
        *,
        attempts: int = 2,
        backoff_seconds: float = 2.0,
    ) -> RawDocument:
        """Fetch a single document with bounded retry on transient errors.

        ``attempts=2`` means: try, fail, retry once, fail for real. Catches
        the common case of a network blip or upstream 5xx during a long
        ingest. Non-transient errors (4xx, decode errors, etc.) propagate
        on the first try -- retrying won't help.
        """
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.to_thread(connector.fetch_document, ref)
            except Exception as e:  # noqa: BLE001
                last_error = e
                msg = str(e).lower()
                # Retry on transport / 5xx markers; bail on auth / not-found.
                transient = any(
                    marker in msg
                    for marker in ("500", "502", "503", "504", "timeout", "connection")
                )
                if not transient or attempt >= attempts:
                    raise
                log.warning(
                    "fetch_document_retry",
                    index=idx,
                    path=ref.source_path,
                    attempt=attempt,
                    error=str(e)[:200],
                )
                await asyncio.sleep(backoff_seconds)
        # Unreachable -- the loop either returns or raises -- but mypy is
        # happier with an explicit raise.
        assert last_error is not None
        raise last_error

    async def close(self) -> None:
        # All repos share the same Postgres pool; close() is a no-op for
        # the non-owners but kept symmetric for the test path that hands
        # in a private DSN.
        await self.registry.close()
        await self.store.close()
        await self.org_repo.close()
        await self.team_repo.close()
        await self.service_repo.close()
        await self.source_repo.close()
