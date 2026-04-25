"""OpenSearch index + bulk indexing helpers.

The index mapping picks up three new fields for the declared model --
``org_id``, ``team_id``, ``service_id`` -- so the retrieval layer can push
scope filters down to OpenSearch instead of post-filtering in Python.

The ``setup_index`` path is still idempotent: the mapping is created once per
``(opensearch_url, index_name)`` tuple. Existing indexes created under the
old mapping won't auto-upgrade; the setup script deletes and recreates on
mapping change. That's fine for Phase 1 -- the plan explicitly wipes seed
data as part of the migration -- but we log a clear warning if the mapping
is missing the new fields.
"""

from __future__ import annotations

from threading import Lock
from uuid import UUID

from opensearchpy import OpenSearch, helpers

from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("indexer")

_shared_client: OpenSearch | None = None
_client_lock = Lock()
_configured_indexes: set[tuple[str, str]] = set()


def get_opensearch_client() -> OpenSearch:
    global _shared_client

    if _shared_client is not None:
        return _shared_client

    with _client_lock:
        if _shared_client is None:
            _shared_client = OpenSearch(
                hosts=[settings.opensearch_url],
                use_ssl=False,
                verify_certs=False,
            )
            log.info("opensearch_client_initialized")

    return _shared_client


INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "canonical_chunk_id": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "standard"},
            "embedding": {
                "type": "knn_vector",
                "dimension": settings.embedding_dimension,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {
                        "m": 16,
                        "ef_construction": 128,
                    },
                },
            },
            "source_platform": {"type": "keyword"},
            "source_path": {"type": "keyword"},
            "source_url": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "org_id": {"type": "keyword"},
            "team_id": {"type": "keyword"},
            "service_id": {"type": "keyword"},
            "document_title": {"type": "text"},
            "section_heading": {"type": "text"},
            "team_hint": {"type": "keyword"},
            "service_hint": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "last_modified": {"type": "date"},
            "author": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "total_chunks": {"type": "integer"},
        },
    },
}

SEARCH_PIPELINE = {
    "description": "Hybrid search with score normalization",
    "phase_results_processors": [
        {
            "normalization-processor": {
                "normalization": {"technique": "min_max"},
                "combination": {
                    "technique": "arithmetic_mean",
                    "parameters": {"weights": [0.4, 0.6]},
                },
            }
        }
    ],
}


def setup_index(client: OpenSearch | None = None) -> None:
    client = client or get_opensearch_client()
    index_name = settings.opensearch_index
    config_key = (settings.opensearch_url, index_name)

    if config_key in _configured_indexes:
        return

    with _client_lock:
        if config_key in _configured_indexes:
            return

        if not client.indices.exists(index=index_name):
            client.indices.create(index=index_name, body=INDEX_MAPPING)
            log.info("index_created", index=index_name)
        else:
            # Add the scope fields onto an existing index so the migration
            # from the pre-Phase-1 mapping works without a full rebuild.
            # OpenSearch accepts PUT mapping for *additive* field changes,
            # which is all we need here.
            try:
                client.indices.put_mapping(
                    index=index_name,
                    body={
                        "properties": {
                            "source_id": {"type": "keyword"},
                            "org_id": {"type": "keyword"},
                            "team_id": {"type": "keyword"},
                            "service_id": {"type": "keyword"},
                        }
                    },
                )
                log.info("index_mapping_upgraded", index=index_name)
            except Exception as e:  # noqa: BLE001
                log.warning("index_mapping_upgrade_failed", error=str(e)[:200])

        pipeline_name = "hybrid-search-pipeline"
        client.http.put(f"/_search/pipeline/{pipeline_name}", body=SEARCH_PIPELINE)
        log.info("search_pipeline_created", pipeline=pipeline_name)

        client.indices.put_settings(
            index=index_name,
            body={"index.search.default_pipeline": pipeline_name},
        )
        log.info("default_pipeline_set", index=index_name, pipeline=pipeline_name)
        _configured_indexes.add(config_key)


def _uuid_str(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def index_chunks(
    chunks: list[Chunk],
    client: OpenSearch | None = None,
    *,
    source_id: UUID | str | None = None,
) -> tuple[int, list[dict]]:
    """Bulk-index chunks. Returns ``(success_count, error_items)``.

    ``error_items`` is the raw list returned by ``helpers.bulk`` when an
    item fails -- callers (the ingest pipeline) lift this into the source's
    ``last_error`` so a partial failure can't silently leave the source
    marked ``ready``.
    """
    if not chunks:
        return 0, []

    client = client or get_opensearch_client()
    index_name = settings.opensearch_index

    actions = []
    for chunk in chunks:
        doc = {
            "_index": index_name,
            "_id": chunk.chunk_id,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "canonical_chunk_id": chunk.canonical_chunk_id,
            "content": chunk.content,
            "embedding": chunk.embedding,
            "source_platform": chunk.metadata.source_platform,
            "source_path": chunk.metadata.source_path,
            "source_url": chunk.metadata.source_url,
            "source_id": _uuid_str(source_id),
            "org_id": _uuid_str(chunk.metadata.org_id),
            "team_id": _uuid_str(chunk.metadata.team_id),
            "service_id": _uuid_str(chunk.metadata.service_id),
            "document_title": chunk.metadata.document_title,
            "section_heading": chunk.metadata.section_heading,
            "team_hint": chunk.metadata.team_hint,
            "service_hint": chunk.metadata.service_hint,
            "doc_type": chunk.metadata.doc_type,
            "last_modified": chunk.metadata.last_modified.isoformat() if chunk.metadata.last_modified else None,
            "author": chunk.metadata.author,
            "chunk_index": chunk.metadata.chunk_index,
            "total_chunks": chunk.metadata.total_chunks,
        }
        actions.append(doc)

    success, errors = helpers.bulk(client, actions, raise_on_error=False)
    if errors:
        log.error("index_errors", count=len(errors), first_error=str(errors[0])[:200])
    else:
        log.info("chunks_indexed", count=success)

    return success, errors


def delete_by_document_id(document_id: str, client: OpenSearch | None = None) -> int:
    client = client or get_opensearch_client()
    index_name = settings.opensearch_index

    response = client.delete_by_query(
        index=index_name,
        body={"query": {"term": {"document_id": document_id}}},
        refresh=True,
    )
    deleted = response.get("deleted", 0)
    log.info("chunks_deleted", document_id=document_id, count=deleted)
    return deleted


def delete_by_source_id(source_id: UUID | str, client: OpenSearch | None = None) -> int:
    """Delete every chunk belonging to a declared source.

    Called when a source is deleted from the catalog, and (optionally) when a
    source is re-ingested with ``force=True``.
    """
    client = client or get_opensearch_client()
    index_name = settings.opensearch_index

    response = client.delete_by_query(
        index=index_name,
        body={"query": {"term": {"source_id": _uuid_str(source_id)}}},
        refresh=True,
    )
    deleted = response.get("deleted", 0)
    log.info("chunks_deleted_by_source", source_id=str(source_id), count=deleted)
    return deleted


def close_opensearch_client() -> None:
    global _shared_client

    if _shared_client is None:
        return

    with _client_lock:
        if _shared_client is not None:
            _shared_client.close()
            _shared_client = None
            _configured_indexes.clear()
            log.info("opensearch_client_closed")
