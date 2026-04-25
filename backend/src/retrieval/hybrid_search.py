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
    """Resolve scope IDs against the catalog and constrain by ``org_id``.

    Three jobs, all of them necessary to keep retrieval honest:

    1. Add parent team_ids for the resolvable services. Without this the
       team clause's ``IS NULL OR team_id IN (...)`` branch admits team-
       scoped chunks for *other* teams in the same org -- the IS NULL
       branch is too permissive when the caller's intent was "chunks
       reachable from these services".
    2. Drop *unresolved* service / team IDs from the returned filter --
       a stale UUID (deleted service, bookmark from another org) would
       otherwise leave the unresolved ID in the list. The clause becomes
       ``service_id IS NULL OR service_id IN [unknown-uuid]`` and the
       IS NULL branch admits every team-scoped chunk in the broader
       scope.
    3. Cross-org guard: when the caller pinned ``org_id``, drop any
       service whose parent team belongs to a *different* org and any
       team that belongs to a different org. Without this, a stale
       bookmark with ``org_id = A`` and ``service_id`` from org B
       resolves cleanly (the service exists), the parent team is added
       to ``team_ids``, and the resulting OpenSearch clauses widen org
       A's match set to org A's org-scoped chunks. The expected
       behavior is "no results" because the caller's filter has no
       in-org targets.

    If no requested service / team survives validation, the filter is
    pinned to ``__match_nothing__`` so the clause builder emits a
    match-none clause.

    The async DB-backed parts (looking up services + teams) are
    decoupled from the pure validation logic so the validation can be
    unit-tested without Postgres.
    """
    if not scope_filter:
        return scope_filter
    service_ids = _collect_ids(scope_filter.get("service_ids"))
    team_ids = _collect_ids(scope_filter.get("team_ids"))
    if not service_ids and not team_ids:
        return scope_filter

    service_lookups, team_lookups = await _resolve_scope_lookups(
        service_ids, team_ids
    )
    return _validate_scope_against_lookups(
        scope_filter,
        service_lookups=service_lookups,
        team_lookups=team_lookups,
    )


async def _resolve_scope_lookups(
    service_ids: list[str],
    team_ids: list[str],
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """Pull (team_id, org_id) for each service and org_id for each team.

    Returns ``(service_lookups, team_lookups)`` where:
      - ``service_lookups[service_id] = (team_id, org_id)`` for every
        service whose ID parsed as UUID, exists, and has a resolvable
        parent team.
      - ``team_lookups[team_id] = org_id`` for every team that exists.

    IDs that don't parse, don't exist, or don't have a parent (orphan
    services without a team -- shouldn't happen given the FK, but we
    treat it as "not validated") are simply absent from the maps.
    Validation downstream treats absence as "drop this ID".
    """
    if not service_ids and not team_ids:
        return {}, {}

    # Lazy imports to avoid a circular dep at module load time.
    from src.catalog.service_repo import ServiceRepository
    from src.catalog.team_repo import TeamRepository
    from uuid import UUID as _UUID

    service_repo = await ServiceRepository.create()
    team_repo = await TeamRepository.create()
    try:
        service_lookups: dict[str, tuple[str, str]] = {}
        # We may need a team's org for both validation paths. Memoize so
        # a service whose parent team is also explicitly in ``team_ids``
        # only costs one query.
        team_org_cache: dict[str, str] = {}

        async def _team_org(team_id: str) -> str | None:
            if team_id in team_org_cache:
                return team_org_cache[team_id]
            try:
                t = await team_repo.get(_UUID(team_id))
            except (ValueError, TypeError):
                return None
            if t is None:
                return None
            org = str(t.org_id)
            team_org_cache[team_id] = org
            return org

        for sid in service_ids:
            try:
                svc = await service_repo.get(_UUID(sid))
            except (ValueError, TypeError):
                continue
            if svc is None or svc.team_id is None:
                continue
            team_id = str(svc.team_id)
            org = await _team_org(team_id)
            if org is None:
                continue
            service_lookups[str(svc.id)] = (team_id, org)

        team_lookups: dict[str, str] = {}
        for tid in team_ids:
            org = await _team_org(tid)
            if org is None:
                continue
            team_lookups[tid] = org
    finally:
        await team_repo.close()
        await service_repo.close()

    return service_lookups, team_lookups


def _validate_scope_against_lookups(
    scope_filter: dict,
    *,
    service_lookups: dict[str, tuple[str, str]],
    team_lookups: dict[str, str],
) -> dict:
    """Pure validation: drop IDs that don't belong to the requested org,
    derive parent teams for surviving services, and emit the
    ``__match_nothing__`` sentinel if nothing the caller asked for
    survives.

    The function is intentionally synchronous and side-effect-free so it
    can be unit-tested against in-memory lookup tables without Postgres.
    """
    requested_service_ids = _collect_ids(scope_filter.get("service_ids"))
    requested_team_ids = _collect_ids(scope_filter.get("team_ids"))
    requested_org = scope_filter.get("org_id")
    expected_org = str(requested_org) if requested_org else None

    resolved_service_ids: set[str] = set()
    parent_team_ids: set[str] = set()
    for sid in requested_service_ids:
        info = service_lookups.get(sid)
        if info is None:
            continue
        team_id, svc_org = info
        if expected_org is not None and svc_org != expected_org:
            # Cross-org service ID: silently dropped. Logged so an
            # operator looking at retrieval traces can see the gap.
            log.warning(
                "scope_service_id_dropped_cross_org",
                service_id=sid,
                expected_org=expected_org,
                actual_org=svc_org,
            )
            continue
        resolved_service_ids.add(sid)
        parent_team_ids.add(team_id)

    resolved_team_ids: set[str] = set()
    for tid in requested_team_ids:
        team_org = team_lookups.get(tid)
        if team_org is None:
            continue
        if expected_org is not None and team_org != expected_org:
            log.warning(
                "scope_team_id_dropped_cross_org",
                team_id=tid,
                expected_org=expected_org,
                actual_org=team_org,
            )
            continue
        resolved_team_ids.add(tid)

    expanded = dict(scope_filter)

    asked_for_services = bool(requested_service_ids)
    asked_for_teams = bool(requested_team_ids)
    services_empty_after = asked_for_services and not resolved_service_ids
    teams_empty_after = asked_for_teams and not resolved_team_ids

    # ``__match_nothing__`` fires when every narrowing axis the caller
    # specified resolves to zero. If the caller only narrowed by
    # services and none survived, that's match-nothing -- same for
    # teams-only. Mixed (services + teams) match-nothings only when
    # *both* survived to zero, because either one alone surviving is
    # still a real (narrower) scope to honor.
    if asked_for_services and asked_for_teams:
        if services_empty_after and teams_empty_after:
            log.warning("scope_all_targets_dropped")
            expanded["__match_nothing__"] = True
            return expanded
    elif asked_for_services and services_empty_after:
        log.warning("scope_service_ids_all_unresolved", requested=len(requested_service_ids))
        expanded["__match_nothing__"] = True
        return expanded
    elif asked_for_teams and teams_empty_after:
        log.warning("scope_team_ids_all_unresolved", requested=len(requested_team_ids))
        expanded["__match_nothing__"] = True
        return expanded

    if asked_for_services:
        expanded["service_ids"] = sorted(resolved_service_ids)
        if len(resolved_service_ids) != len(requested_service_ids):
            log.warning(
                "scope_service_ids_partially_resolved",
                requested=len(requested_service_ids),
                resolved=len(resolved_service_ids),
            )

    if asked_for_teams or parent_team_ids:
        # Surviving explicit teams + parent teams of surviving services.
        # Dropping the explicit team list when the caller passed one but
        # nothing survived would silently widen the scope; we already
        # bailed to match_nothing in that branch above.
        merged_teams = resolved_team_ids | parent_team_ids
        expanded["team_ids"] = sorted(merged_teams)
        if asked_for_teams and len(resolved_team_ids) != len(requested_team_ids):
            log.warning(
                "scope_team_ids_partially_resolved",
                requested=len(requested_team_ids),
                resolved=len(resolved_team_ids),
            )

    return expanded


def _build_scope_clauses(scope_filter: dict) -> list[dict]:
    """Turn ``{org_id, team_ids, service_ids}`` into OpenSearch bool clauses.

    The model:
    - ``org_id`` is a hard filter: only chunks from that org ever match.
    - ``team_ids`` and ``service_ids`` use the *nullable OR equal* pattern:
      a chunk matches if its team/service is NULL **or** in the allow-list.
      ``NULL`` means the chunk is org-scoped (or team-scoped, respectively),
      so it's in scope by inheritance.
    - ``__match_nothing__`` short-circuits to a clause no chunk satisfies;
      see ``_expand_scope_with_service_parents`` for when this is set.
    """
    if scope_filter.get("__match_nothing__"):
        # ``must_not: match_all`` is the canonical "match no documents"
        # clause in OpenSearch -- safer than relying on a sentinel UUID
        # that *might* coincide with a real chunk.
        return [{"bool": {"must_not": {"match_all": {}}}}]

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
