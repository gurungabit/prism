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
from src.connectors.base import SourceConfig
from src.connectors.base import ConnectorRegistry
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
from src.models.chunk import Chunk
from src.models.document import RawDocument
from src.observability.logging import get_logger

log = get_logger("pipeline")


@dataclass
class PreparedDocument:
    document_id: str
    raw_doc: RawDocument
    parsed_content: str
    content_hash: str
    chunks: list[Chunk] = field(default_factory=list)


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

        if force:
            # Remove every existing chunk + registry entry for this source so
            # the re-ingest re-issues fresh document ids. Without this the
            # content-hash skip would keep old OpenSearch entries around.
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
            raise
        finally:
            await connector.aclose()

        # Per-document parse / index failures, or any OpenSearch bulk error,
        # used to be silently masked because the source flipped to ``ready``
        # regardless. Surface them: status -> error, last_error carries a
        # short diagnostic the UI can show. The source still keeps whatever
        # chunks did land (we don't roll back partial success), but the user
        # knows to retry.
        failed_count = int(stats.get("failed", 0) or 0)
        index_errors = int(stats.get("index_errors", 0) or 0)
        if failed_count or index_errors:
            parts: list[str] = []
            if failed_count:
                parts.append(f"{failed_count} document(s) failed to parse/index")
            if index_errors:
                parts.append(f"{index_errors} OpenSearch bulk error(s)")
            first_err = stats.get("index_first_error")
            if first_err:
                parts.append(f"first: {first_err}")
            await self.source_repo.mark_status(
                source_id,
                SourceStatus.ERROR,
                last_error="; ".join(parts)[:500],
                last_ingested_at=datetime.now(tz=timezone.utc),
            )
        else:
            await self.source_repo.mark_status(
                source_id,
                SourceStatus.READY,
                last_error=None,
                last_ingested_at=datetime.now(tz=timezone.utc),
            )
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

    async def _ingest_with_connector(
        self,
        connector,
        source: Source,
        scope: SourceScope,
        *,
        force: bool,
    ) -> dict[str, Any]:
        stats: dict[str, Any] = {"total": 0, "indexed": 0, "skipped": 0, "failed": 0}

        try:
            doc_refs = connector.list_documents()
        except Exception as e:  # noqa: BLE001
            log.error("list_documents_failed", source=source.name, error=str(e))
            raise

        log.info("documents_found", source=source.name, count=len(doc_refs))
        stats["total"] = len(doc_refs)

        prepared: list[PreparedDocument] = []

        log.info("phase_1_parse_chunk", source=source.name, total=len(doc_refs))
        for idx, ref in enumerate(doc_refs, start=1):
            try:
                log.info(
                    "fetch_document_start",
                    source=source.name,
                    index=idx,
                    total=len(doc_refs),
                    path=ref.source_path,
                )
                # Connector uses a sync httpx.Client; run per-doc fetches on a
                # worker thread so the event loop stays responsive for the UI
                # while we walk a large repo.
                raw_doc = await asyncio.to_thread(connector.fetch_document, ref)
                log.info(
                    "fetch_document_ok",
                    source=source.name,
                    index=idx,
                    path=ref.source_path,
                )
                content = raw_doc.content if isinstance(raw_doc.content, str) else raw_doc.content
                content_hash = compute_content_hash(content)

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
                        continue

                    if existing:
                        # Drop the stale chunk set before re-indexing with a
                        # new document_id. The new kg_documents row (same id)
                        # is overwritten via ON CONFLICT below.
                        # delete_by_query w/ refresh=True is sync and can
                        # block the event loop for seconds, so push to a
                        # worker thread.
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

                document_id = str(uuid.uuid4())
                parsed_content = parse_document(raw_doc)
                log.info(
                    "parsed",
                    source=source.name,
                    index=idx,
                    content_len=len(parsed_content),
                )

                if not parsed_content.strip():
                    stats["failed"] += 1
                    continue

                chunks = chunk_document(document_id, parsed_content, raw_doc)
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
                    )
                )

            except Exception as e:  # noqa: BLE001
                log.error("document_parse_failed", path=ref.source_path, error=str(e))
                stats["failed"] += 1

        if not prepared:
            log.info("no_documents_to_index", source=source.name)
            return stats

        log.info("phase_2_embed", source=source.name, documents=len(prepared))
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
            except Exception as e:  # noqa: BLE001
                log.error("graph_populate_failed", path=doc.raw_doc.ref.source_path, error=str(e))
                stats["failed"] += 1

        # Tombstone phase: any registry row whose path didn't show up on this
        # ingest's upstream listing is stale -- the doc was removed/renamed
        # upstream and we shouldn't keep its chunks searchable.
        upstream_paths = {ref.source_path for ref in doc_refs}
        existing_for_source = await self.registry.get_for_source(source.id)
        stale_paths = [
            row["source_path"]
            for row in existing_for_source
            if row["source_path"] not in upstream_paths
        ]
        if stale_paths:
            log.info(
                "tombstoning_removed_docs",
                source=source.name,
                count=len(stale_paths),
            )
            removed_doc_ids = await self.registry.delete_by_paths(
                source.id, stale_paths
            )
            for doc_id in removed_doc_ids:
                try:
                    await asyncio.to_thread(
                        delete_by_document_id, doc_id, self.os_client
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "tombstone_opensearch_delete_failed",
                        document_id=doc_id,
                        error=str(e)[:200],
                    )
            stats["tombstoned"] = len(removed_doc_ids)

        log.info(
            "source_complete",
            source=source.name,
            indexed=stats["indexed"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            tombstoned=stats.get("tombstoned", 0),
            index_errors=stats.get("index_errors", 0),
        )
        return stats

    def _stamp_scope_onto_chunks(self, chunks: list[Chunk], scope: SourceScope) -> None:
        for chunk in chunks:
            chunk.metadata.org_id = scope.org_id
            chunk.metadata.team_id = scope.team_id
            chunk.metadata.service_id = scope.service_id

    async def close(self) -> None:
        # The catalog repos share the DSN with the registry/store, so they
        # all close the same shared pool. We only need to close the ones that
        # may own a private pool (none do in practice, but we call close
        # defensively).
        await self.registry.close()
        await self.store.close()
        await self.org_repo.close()
        await self.team_repo.close()
        await self.service_repo.close()
        await self.source_repo.close()
