from __future__ import annotations

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
    ) -> list[Chunk]:
        top_k = top_k or settings.retrieval_top_k

        if expand:
            queries = await expand_queries(requirement)
        else:
            queries = [requirement]

        all_results: list[list[Chunk]] = []

        for q in queries:
            bm25_results = self._bm25_search(q, top_k, filters)
            all_results.append(bm25_results)

        query_embedding = embed_query(requirement)
        vector_results = self._vector_search(query_embedding, top_k, filters)
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
        )
        return result

    def _bm25_search(
        self,
        query_text: str,
        top_k: int,
        filters: dict | None = None,
    ) -> list[Chunk]:
        body: dict = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [{"match": {"content": {"query": query_text}}}],
                }
            },
        }

        if filters:
            filter_clauses = self._build_filters(filters)
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

        if filters:
            body["query"] = {
                "bool": {
                    "must": [body["query"]],
                    "filter": self._build_filters(filters),
                }
            }

        try:
            response = self.client.search(index=self.index_name, body=body)
            chunks = self._parse_hits(response)
            # Filter low-similarity kNN results.
            # With cosinesimil/nmslib: score = 1/(2 - cos_sim).
            # Threshold 0.6 ≈ cosine similarity > 0.33.
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

    def _build_filters(self, filters: dict) -> list[dict]:
        clauses = []
        if "source_platform" in filters:
            clause = self._build_filter_clause("source_platform", filters["source_platform"])
            if clause:
                clauses.append(clause)
        if "doc_type" in filters:
            clause = self._build_filter_clause("doc_type", filters["doc_type"])
            if clause:
                clauses.append(clause)
        if "team_hint" in filters:
            clause = self._build_filter_clause("team_hint", filters["team_hint"])
            if clause:
                clauses.append(clause)
        if "service_hint" in filters:
            clause = self._build_filter_clause("service_hint", filters["service_hint"])
            if clause:
                clauses.append(clause)
        return clauses

    @staticmethod
    def _build_filter_clause(field: str, value: str | list[str] | tuple[str, ...] | set[str] | None) -> dict | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            values = [item for item in value if item]
            if not values:
                return None
            return {"terms": {field: values}}
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
