from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.config import settings
from src.connectors.base import APIConnector, ConnectorRegistry
from src.ingestion.chunker import chunk_document
from src.ingestion.deduplicator import ChunkDeduplicator
from src.ingestion.embedder import embed_chunks
from src.ingestion.entity_extractor import ExtractedEntities, _regex_fallback
from src.ingestion.graph_builder import KnowledgeGraphBuilder
from src.ingestion.indexer import delete_by_document_id, get_opensearch_client, index_chunks, setup_index
from src.ingestion.parser import parse_document
from src.ingestion.registry import DocumentRegistry, compute_content_hash
from src.ingestion.team_names import canonicalize_team_name
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
    entities: ExtractedEntities = field(default_factory=ExtractedEntities)


class IngestionPipeline:
    def __init__(
        self,
        registry: DocumentRegistry,
        graph_builder: KnowledgeGraphBuilder,
        deduplicator: ChunkDeduplicator | None = None,
    ) -> None:
        self.registry = registry
        self.graph_builder = graph_builder
        self.deduplicator = deduplicator or ChunkDeduplicator()
        self.os_client = get_opensearch_client()

    @classmethod
    async def create(cls) -> IngestionPipeline:
        registry = await DocumentRegistry.create()
        graph_builder = await KnowledgeGraphBuilder.create()
        pipeline = cls(registry, graph_builder)
        setup_index(pipeline.os_client)
        return pipeline

    async def ingest_all(self, data_dir: str | None = None, force: bool = False) -> dict:
        data_dir = data_dir or settings.data_dir
        connectors = ConnectorRegistry.create_all(data_dir)

        stats = {"total": 0, "indexed": 0, "skipped": 0, "failed": 0, "platforms": []}

        for connector in connectors:
            platform_stats = await self._ingest_platform(connector, force)
            stats["total"] += platform_stats["total"]
            stats["indexed"] += platform_stats["indexed"]
            stats["skipped"] += platform_stats["skipped"]
            stats["failed"] += platform_stats["failed"]
            stats["platforms"].append({"platform": connector.platform, **platform_stats})

        cleanup = await self.graph_builder.sanitize_team_nodes()
        stats["team_cleanup"] = cleanup
        log.info("ingestion_complete", **stats)
        return stats

    async def ingest_platform(self, platform: str, data_dir: str | None = None, force: bool = False) -> dict:
        # Check if this is an API connector first
        api_connector = ConnectorRegistry.create_api(platform)
        if api_connector is not None:
            stats = await self._ingest_platform(api_connector, force)
            stats["team_cleanup"] = await self.graph_builder.sanitize_team_nodes()
            if hasattr(api_connector, "close"):
                api_connector.close()
            return stats

        data_dir = data_dir or settings.data_dir
        connector_cls = ConnectorRegistry.get(platform)
        if not connector_cls:
            raise ValueError(f"Unknown platform: {platform}")

        platform_dir = Path(data_dir) / "sources" / platform
        if not platform_dir.exists():
            raise FileNotFoundError(f"Platform directory not found: {platform_dir}")

        connector = connector_cls(platform_dir)
        stats = await self._ingest_platform(connector, force)
        stats["team_cleanup"] = await self.graph_builder.sanitize_team_nodes()
        return stats

    async def _ingest_platform(self, connector, force: bool) -> dict:
        stats = {"total": 0, "indexed": 0, "skipped": 0, "failed": 0}

        try:
            doc_refs = connector.list_documents()
        except Exception as e:
            log.error("list_documents_failed", platform=connector.platform, error=str(e))
            return stats

        log.info("documents_found", platform=connector.platform, count=len(doc_refs))
        stats["total"] = len(doc_refs)

        prepared: list[PreparedDocument] = []

        log.info("phase_1_parse_chunk", platform=connector.platform)
        for ref in doc_refs:
            try:
                raw_doc = connector.fetch_document(ref)
                content_for_hash = raw_doc.content if isinstance(raw_doc.content, str) else raw_doc.content
                content_hash = compute_content_hash(content_for_hash)

                if not force:
                    existing = await self.registry.get_by_path(ref.source_path)
                    if existing and existing["content_hash"] == content_hash:
                        stats["skipped"] += 1
                        continue

                    if existing:
                        delete_by_document_id(existing["document_id"], self.os_client)
                        await self.graph_builder.remove_document_edges(existing["document_id"])

                document_id = str(uuid.uuid4())
                parsed_content = parse_document(raw_doc)

                if not parsed_content.strip():
                    stats["failed"] += 1
                    continue

                chunks = chunk_document(document_id, parsed_content, raw_doc)

                for chunk in chunks:
                    canonical = self.deduplicator.check_duplicate(chunk.chunk_id, chunk.content)
                    if canonical:
                        chunk.canonical_chunk_id = canonical

                entities = _regex_fallback(parsed_content, raw_doc.ref.source_path)

                prepared.append(
                    PreparedDocument(
                        document_id=document_id,
                        raw_doc=raw_doc,
                        parsed_content=parsed_content,
                        content_hash=content_hash,
                        chunks=chunks,
                        entities=entities,
                    )
                )

            except Exception as e:
                log.error("document_parse_failed", path=ref.source_path, error=str(e))
                stats["failed"] += 1

        if not prepared:
            log.info("no_documents_to_index", platform=connector.platform)
            return stats

        log.info("phase_2_embed", platform=connector.platform, documents=len(prepared))
        all_chunks = []
        for doc in prepared:
            all_chunks.extend(doc.chunks)

        all_chunks = embed_chunks(all_chunks, batch_size=256)
        log.info("embedding_complete", total_chunks=len(all_chunks))

        log.info("phase_3_index", platform=connector.platform, chunks=len(all_chunks))
        indexed = index_chunks(all_chunks, self.os_client)
        log.info("opensearch_indexed", count=indexed)

        log.info("phase_4_graph", platform=connector.platform, documents=len(prepared))
        for doc in prepared:
            try:
                await self.graph_builder.add_document(doc.document_id, doc.raw_doc)
                await self._populate_graph_from_entities(doc.entities, doc.document_id, doc.raw_doc.ref.source_path)

                await self.registry.upsert(
                    document_id=doc.document_id,
                    source_platform=doc.raw_doc.ref.source_platform,
                    source_path=doc.raw_doc.ref.source_path,
                    content_hash=doc.content_hash,
                    chunk_count=len(doc.chunks),
                    status="indexed",
                )

                stats["indexed"] += 1
            except Exception as e:
                log.error("graph_populate_failed", path=doc.raw_doc.ref.source_path, error=str(e))
                stats["failed"] += 1

        log.info(
            "platform_complete",
            platform=connector.platform,
            indexed=stats["indexed"],
            skipped=stats["skipped"],
            failed=stats["failed"],
        )
        return stats

    async def _populate_graph_from_entities(
        self,
        entities: ExtractedEntities,
        document_id: str,
        source_path: str,
    ) -> None:
        seen_teams: set[str] = set()
        seen_services: set[str] = set()

        for team_data in entities.teams:
            team_name = _normalize_team_name(team_data.get("name", ""))
            if not team_name or team_name in seen_teams:
                continue
            seen_teams.add(team_name)

            await self.graph_builder.add_team(team_name)
            for service_name in team_data.get("owns", []):
                svc = service_name.strip()
                if svc:
                    await self.graph_builder.add_ownership(team_name, svc, "inferred", source_path)

        for svc_data in entities.services:
            service_name = svc_data.get("name", "").strip()
            if not service_name or service_name in seen_services:
                continue
            seen_services.add(service_name)

            await self.graph_builder.add_service(service_name)
            await self.graph_builder.add_document_reference(document_id, service_name)

            for dep in svc_data.get("depends_on", []):
                if dep.strip():
                    await self.graph_builder.add_dependency(service_name, dep.strip(), source_path)

        for dep in entities.dependencies:
            from_svc = dep.get("from", "").strip()
            to_svc = dep.get("to", "").strip()
            if from_svc and to_svc:
                await self.graph_builder.add_dependency(from_svc, to_svc, source_path)

    async def close(self) -> None:
        await self.registry.close()
        await self.graph_builder.close()


def _normalize_team_name(name: str) -> str:
    return canonicalize_team_name(name) or ""
