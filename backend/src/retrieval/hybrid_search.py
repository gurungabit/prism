"""Hybrid (BM25 + vector) retrieval with declared-scope filtering.

Retrieval accepts an optional ``scope_filter`` that maps directly to the plan:

    WHERE org_id = Z
      AND (team_id    IS NULL OR team_id    = X)
      AND (service_id IS NULL OR service_id = Y)

i.e. org-scoped chunks always match; team / service-scoped chunks match only
when in scope. The filter is pushed down into OpenSearch as ``should`` /
``must_not`` clauses so it happens at retrieval time, not after scoring.
"""

from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from opensearchpy import OpenSearch

from src.config import settings
from src.ingestion.embedder import embed_query
from src.ingestion.indexer import get_opensearch_client
from src.models.chunk import Chunk, ChunkMetadata
from src.observability.logging import get_logger
from src.retrieval.query_expansion import expand_queries

log = get_logger("hybrid_search")


class HybridSearchEngine:
    def __init__(self, client: OpenSearch | None = None) -> None:
        self.client = client or get_opensearch_client()
        self.index_name = settings.opensearch_index

    async def search(
        self,
        requirement: str,
        top_k: int | None = None,
        filters: dict | None = None,
        expand: bool = True,
        *,
        scope_filter: dict | None = None,
    ) -> list[Chunk]:
        top_k = top_k or settings.retrieval_top_k

        # Expand the scope before query execution: when the caller passed
        # service_ids without explicit team_ids, derive the parent teams so
        # team-scoped chunks for *other* teams in the same org can't slip
        # through the nullable-OR clause. Without this, picking only
        # ``auth-service`` would still admit, say, ``payments-team`` team
        # docs because the service clause's ``IS NULL`` branch admits them.
        scope_filter = await _expand_scope_with_service_parents(scope_filter)

        if expand:
            queries = await expand_queries(requirement)
        else:
            queries = [requirement]

        # Merge the caller's ``filters`` with the declared-scope filter. The
        # scope filter lives on its own because it's the one that uses
        # bool/should semantics (nullability matters); ``filters`` stays as
        # plain term/terms clauses.
        merged_filters = dict(filters or {})

        all_results: list[list[Chunk]] = []

        for q in queries:
            bm25_results = self._bm25_search(q, top_k, merged_filters, scope_filter)
            all_results.append(bm25_results)

        query_embedding = embed_query(requirement)
        vector_results = self._vector_search(query_embedding, top_k, merged_filters, scope_filter)
        all_results.append(vector_results)

        merged = self._rrf_merge(all_results, k=60)

        deduped = [c for c in merged if c.canonical_chunk_id is None]

        result = deduped[:top_k]
        log.info(
            "hybrid_search_complete",
            queries=len(queries),
            total_candidates=sum(len(r) for r in all_results),
            merged=len(merged),
            deduped=len(deduped),
            returned=len(result),
            scoped=bool(scope_filter),
        )
        return result

    # ----- per-query runners -----

    def _bm25_search(
        self,
        query_text: str,
        top_k: int,
        filters: dict | None = None,
        scope_filter: dict | None = None,
    ) -> list[Chunk]:
        body: dict = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [{"match": {"content": {"query": query_text}}}],
                }
            },
        }

        filter_clauses = self._combine_filters(filters, scope_filter)
        if filter_clauses:
            body["query"]["bool"]["filter"] = filter_clauses

        try:
            response = self.client.search(index=self.index_name, body=body)
            return self._parse_hits(response)
        except Exception as e:
            log.error("bm25_search_failed", error=str(e))
            return []

    def _vector_search(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict | None = None,
        scope_filter: dict | None = None,
        min_score: float = 0.6,
    ) -> list[Chunk]:
        body: dict = {
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k": top_k,
                    }
                }
            },
        }

        filter_clauses = self._combine_filters(filters, scope_filter)
        if filter_clauses:
            body["query"] = {
                "bool": {
                    "must": [body["query"]],
                    "filter": filter_clauses,
                }
            }

        try:
            response = self.client.search(index=self.index_name, body=body)
            chunks = self._parse_hits(response)
            if min_score:
                before = len(chunks)
                chunks = [c for c in chunks if c.score >= min_score]
                if before != len(chunks):
                    log.info(
                        "vector_results_filtered",
                        before=before,
                        after=len(chunks),
                        min_score=min_score,
                    )
            return chunks
        except Exception as e:
            log.error("vector_search_failed", error=str(e))
            return []

    def _hybrid_search_native(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[Chunk]:
        body = {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        {"match": {"content": {"query": query_text}}},
                        {"knn": {"embedding": {"vector": query_vector, "k": top_k}}},
                    ]
                }
            },
        }

        try:
            response = self.client.search(
                index=self.index_name,
                body=body,
                params={"search_pipeline": "hybrid-search-pipeline"},
            )
            return self._parse_hits(response)
        except Exception as e:
            log.warning("native_hybrid_search_failed_falling_back", error=str(e))
            return []

    def _rrf_merge(self, result_lists: list[list[Chunk]], k: int = 60) -> list[Chunk]:
        chunk_map: dict[str, Chunk] = {}
        scores: dict[str, float] = {}

        for result_list in result_lists:
            for rank, chunk in enumerate(result_list):
                cid = chunk.chunk_id
                if cid not in chunk_map:
                    chunk_map[cid] = chunk
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        result = []
        for cid in sorted_ids:
            chunk = chunk_map[cid]
            chunk.score = scores[cid]
            result.append(chunk)

        return result

    # ----- filter composition -----

    def _combine_filters(
        self,
        filters: dict | None,
        scope_filter: dict | None,
    ) -> list[dict]:
        clauses = self._build_filters(filters) if filters else []
        if scope_filter:
            scope_clauses = _build_scope_clauses(scope_filter)
            clauses.extend(scope_clauses)
        return clauses

    def _build_filters(self, filters: dict) -> list[dict]:
        clauses = []
        for field in ("source_platform", "doc_type", "team_hint", "service_hint", "org_id", "team_id", "service_id"):
            if field in filters:
                clause = self._build_filter_clause(field, filters[field])
                if clause:
                    clauses.append(clause)
        return clauses

    @staticmethod
    def _build_filter_clause(field: str, value: Any) -> dict | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            values = [str(item) for item in value if item not in (None, "")]
            if not values:
                return None
            return {"terms": {field: values}}
        if isinstance(value, UUID):
            return {"term": {field: str(value)}}
        if value == "":
            return None
        return {"term": {field: value}}

    def _parse_hits(self, response: dict) -> list[Chunk]:
        chunks = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            try:
                metadata = ChunkMetadata(
                    source_platform=source.get("source_platform", "gitlab"),
                    source_path=source.get("source_path", ""),
                    source_url=source.get("source_url", ""),
                    document_title=source.get("document_title", ""),
                    section_heading=source.get("section_heading", ""),
                    team_hint=source.get("team_hint", ""),
                    service_hint=source.get("service_hint", ""),
                    org_id=source.get("org_id"),
                    team_id=source.get("team_id"),
                    service_id=source.get("service_id"),
                    doc_type=source.get("doc_type", "unknown"),
                    last_modified=source.get("last_modified"),
                    author=source.get("author", ""),
                    chunk_index=source.get("chunk_index", 0),
                    total_chunks=source.get("total_chunks", 1),
                )
                chunk = Chunk(
                    chunk_id=source.get("chunk_id", hit["_id"]),
                    document_id=source.get("document_id", ""),
                    content=source.get("content", ""),
                    metadata=metadata,
                    canonical_chunk_id=source.get("canonical_chunk_id"),
                    score=hit.get("_score", 0.0),
                )
                chunks.append(chunk)
            except Exception as e:
                log.warning("parse_hit_failed", hit_id=hit.get("_id"), error=str(e))
                continue
        return chunks


async def _expand_scope_with_service_parents(
    scope_filter: dict | None,
) -> dict | None:
    """Add parent team_ids for any selected service_ids.

    Without this expansion the OpenSearch clause builder would emit a
    ``team_id IS NULL OR team_id IN (...)`` branch off the explicit
    ``team_ids`` list only -- selecting just a service would still admit
    team-scoped chunks for *other* teams in the same org because the
    nullable branch accepts any team-scoped chunk. Pre-deriving the
    parent teams pins the team clause to the union of (explicit teams) +
    (services' parent teams), which is the right semantic for "I want
    chunks reachable from these services".

    Returns the scope dict (possibly mutated copy) or ``None`` when no
    scope was supplied.
    """
    if not scope_filter:
        return scope_filter
    service_ids = _collect_ids(scope_filter.get("service_ids"))
    if not service_ids:
        return scope_filter

    # Lazy import to avoid a circular dep at module load time.
    from src.catalog.service_repo import ServiceRepository
    from uuid import UUID as _UUID

    repo = await ServiceRepository.create()
    try:
        parent_team_ids: set[str] = set()
        for sid in service_ids:
            try:
                service = await repo.get(_UUID(sid))
            except (ValueError, TypeError):
                continue
            if service is not None and service.team_id is not None:
                parent_team_ids.add(str(service.team_id))
    finally:
        await repo.close()

    if not parent_team_ids:
        return scope_filter

    expanded = dict(scope_filter)
    existing_teams = set(_collect_ids(scope_filter.get("team_ids")))
    expanded["team_ids"] = sorted(existing_teams | parent_team_ids)
    return expanded


def _build_scope_clauses(scope_filter: dict) -> list[dict]:
    """Turn ``{org_id, team_ids, service_ids}`` into OpenSearch bool clauses.

    The model:
    - ``org_id`` is a hard filter: only chunks from that org ever match.
    - ``team_ids`` and ``service_ids`` use the *nullable OR equal* pattern:
      a chunk matches if its team/service is NULL **or** in the allow-list.
      ``NULL`` means the chunk is org-scoped (or team-scoped, respectively),
      so it's in scope by inheritance.
    """
    clauses: list[dict] = []

    org_id = scope_filter.get("org_id")
    if org_id:
        clauses.append({"term": {"org_id": str(org_id)}})

    team_ids = _collect_ids(scope_filter.get("team_ids"))
    if team_ids:
        # match team_id IS NULL OR team_id IN (team_ids)
        clauses.append(
            {
                "bool": {
                    "should": [
                        {"bool": {"must_not": {"exists": {"field": "team_id"}}}},
                        {"terms": {"team_id": team_ids}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    service_ids = _collect_ids(scope_filter.get("service_ids"))
    if service_ids:
        clauses.append(
            {
                "bool": {
                    "should": [
                        {"bool": {"must_not": {"exists": {"field": "service_id"}}}},
                        {"terms": {"service_id": service_ids}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    return clauses


def _collect_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, UUID)):
        return [str(value)]
    if isinstance(value, Iterable):
        return [str(v) for v in value if v not in (None, "")]
    return [str(value)]
