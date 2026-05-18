from __future__ import annotations

from typing import Any
from uuid import UUID

from src.agents.result import AgentResult
from src.agents.state_codec import normalize_agent_result, normalize_chunks
from src.agents.step_callbacks import get_step_callback
from src.catalog import ServiceRepository, TeamRepository
from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.hybrid_search import HybridSearchEngine, RetrievalUnavailable
from src.retrieval.refiner import maybe_refine_retrieval

log = get_logger("retrieval_agent")

MIN_RELEVANT_CHUNKS = 3
MIN_RELEVANCE_SCORE = 0.3


async def retrieval_agent(state: dict[str, Any], *, mode: str = "discovery") -> dict[str, Any]:
    requirement = state.get("search_query") or state["requirement"]
    analysis_id = state.get("analysis_id", "unknown")
    retrieval_rounds = state.get("retrieval_rounds", 0)
    on_step = get_step_callback(state.get("analysis_id"))
    pass_label = "coverage_retry" if mode == "coverage_retry" else mode

    log.info(
        "retrieval_start",
        analysis_id=analysis_id,
        round=retrieval_rounds + 1,
        mode=mode,
    )

    if on_step:
        await on_step(
            {
                "agent": "retrieve",
                "action": "searching",
                "detail": f"Round {retrieval_rounds + 1}: {pass_label.replace('_', ' ')} search...",
            }
        )

    scope_filter = await _scope_filter_for_mode(state, mode=mode)
    queries = _queries_for_mode(state, requirement, mode=mode)

    search_engine = HybridSearchEngine()
    try:
        chunks = await _run_searches(
            search_engine,
            queries,
            scope_filter=scope_filter,
            pass_label=pass_label,
        )
    except RetrievalUnavailable as e:
        log.error(
            "retrieval_unavailable",
            analysis_id=analysis_id,
            error=str(e)[:300],
        )
        if on_step:
            await on_step(
                {
                    "agent": "retrieve",
                    "action": "error",
                    "detail": "Search backend unavailable; cannot complete this analysis.",
                }
            )
        return {
            "retrieved_chunks": [],
            "retrieval_result": AgentResult(
                status="failed",
                error="retrieval_unavailable",
                degradation_note=(
                    "Search backend is currently unavailable. "
                    "Try again in a moment."
                ),
            ),
            "retrieval_rounds": retrieval_rounds + 1,
        }

    chunks = await maybe_refine_retrieval(
        search_engine,
        chunks=chunks,
        original_query=requirement,
        scope_filter=scope_filter,
        enabled=settings.analysis_agentic_refine,
        min_chunks=settings.analysis_refine_min_chunks,
        max_score=settings.analysis_refine_max_score,
        retrieval_top_k=settings.retrieval_top_k,
        query_expansion=True,
        use_hyde=settings.analysis_use_hyde,
        # Agent-specific reranking happens in router/dependency/risk
        # using their own doc-type filters, so keep the raw candidate
        # window intact here.
        rerank_enabled=False,
        rerank_top_k=settings.rerank_top_k,
    )
    _stamp_retrieval_pass(chunks, pass_label)

    if on_step:
        await on_step(
            {
                "agent": "retrieve",
                "action": "results",
                "detail": f"Found {len(chunks)} chunks across documents",
                "data": {
                    "round": retrieval_rounds + 1,
                    "mode": pass_label,
                    "queries": queries,
                    "chunks_found": len(chunks),
                },
            }
        )

    relevant_chunks = [c for c in chunks if c.score > MIN_RELEVANCE_SCORE]

    if len(relevant_chunks) < MIN_RELEVANT_CHUNKS:
        log.warning(
            "insufficient_data",
            analysis_id=analysis_id,
            relevant=len(relevant_chunks),
            total=len(chunks),
        )
        if on_step:
            await on_step(
                {"agent": "retrieve", "action": "complete", "detail": f"Partial: {len(relevant_chunks)} relevant of {len(chunks)} total"}
            )
        return _retrieval_update(
            state,
            chunks,
            mode=mode,
            retrieval_rounds=retrieval_rounds + 1,
            retrieval_result=AgentResult(
                status="partial",
                degradation_note=(
                    f"Found only {len(relevant_chunks)} relevant documents (minimum: {MIN_RELEVANT_CHUNKS}). "
                    "This requirement may involve new capabilities not yet documented. "
                    "Analysis sections will be marked as low confidence."
                ),
            ),
        )

    if on_step:
        await on_step(
            {"agent": "retrieve", "action": "complete", "detail": f"{len(relevant_chunks)} relevant chunks from {len(chunks)} total"}
        )

    log.info(
        "retrieval_complete",
        analysis_id=analysis_id,
        total=len(chunks),
        relevant=len(relevant_chunks),
        mode=mode,
    )

    return _retrieval_update(
        state,
        chunks,
        mode=mode,
        retrieval_rounds=retrieval_rounds + 1,
        retrieval_result=AgentResult(status="success"),
    )


async def _run_searches(
    search_engine: HybridSearchEngine,
    queries: list[str],
    *,
    scope_filter: dict | None,
    pass_label: str,
) -> list[Chunk]:
    collected: list[Chunk] = []
    for query in queries:
        hits = await search_engine.search(
            requirement=query,
            expand=True,
            scope_filter=scope_filter,
            use_hyde=settings.analysis_use_hyde,
        )
        _stamp_retrieval_pass(hits, pass_label)
        collected = _merge_chunks(collected, hits)
    return collected


def _queries_for_mode(state: dict[str, Any], requirement: str, *, mode: str) -> list[str]:
    if mode != "coverage_retry":
        return [requirement]

    coverage = normalize_agent_result(state.get("coverage_report"))
    data = coverage.data if coverage and isinstance(coverage.data, dict) else {}
    targeted = data.get("targeted_searches", []) if isinstance(data, dict) else []
    queries = [str(q).strip() for q in targeted if str(q).strip()]
    return queries or [requirement]


async def _scope_filter_for_mode(state: dict[str, Any], *, mode: str) -> dict | None:
    analysis_input = state.get("analysis_input") or {}
    org_id = analysis_input.get("org_id") if isinstance(analysis_input, dict) else None
    if not org_id:
        return None

    # Discovery deliberately searches the whole selected org so routing can
    # find candidate teams/services before the deep-dive narrows evidence.
    if mode == "discovery":
        return {"org_id": org_id}

    base_team_ids = [str(t) for t in (analysis_input.get("team_ids") or [])]
    base_service_ids = [str(s) for s in (analysis_input.get("service_ids") or [])]
    scope_filter = {
        "org_id": org_id,
        "team_ids": base_team_ids,
        "service_ids": base_service_ids,
    }

    # Explicit user-selected teams/services are hard constraints. If the user
    # picked a narrow scope, the router cannot broaden it; coverage retry uses
    # the same deep scope plus targeted query text.
    if base_service_ids:
        return scope_filter

    routed = await _routed_scope_ids(state, org_id=str(org_id))
    if base_team_ids:
        allowed_teams = set(base_team_ids)
        routed_services = [
            service_id
            for service_id, team_id in routed["service_team_ids"].items()
            if team_id in allowed_teams
        ]
        scope_filter["service_ids"] = sorted(set(base_service_ids) | set(routed_services))
        return scope_filter

    routed_team_ids = set(routed["team_ids"])
    routed_service_ids = set(routed["service_team_ids"].keys())
    if routed_team_ids or routed_service_ids:
        scope_filter["team_ids"] = sorted(routed_team_ids)
        scope_filter["service_ids"] = sorted(routed_service_ids)

    return scope_filter


async def _routed_scope_ids(state: dict[str, Any], *, org_id: str) -> dict[str, Any]:
    routing = normalize_agent_result(state.get("team_routing"))
    data = routing.data if routing and isinstance(routing.data, dict) else {}
    if not data:
        return {"team_ids": [], "service_team_ids": {}}

    team_names: set[str] = set()
    service_names: set[str] = set()

    primary = data.get("primary_team", {})
    if isinstance(primary, dict) and primary.get("name"):
        team_names.add(str(primary["name"]).lower())

    for svc in data.get("affected_services", []) or []:
        if not isinstance(svc, dict):
            continue
        if svc.get("name"):
            service_names.add(str(svc["name"]).lower())
        if svc.get("owning_team"):
            team_names.add(str(svc["owning_team"]).lower())

    if not team_names and not service_names:
        return {"team_ids": [], "service_team_ids": {}}

    try:
        org_uuid = UUID(org_id)
    except (TypeError, ValueError):
        return {"team_ids": [], "service_team_ids": {}}

    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    try:
        teams = await team_repo.list_for_org(org_uuid)
        team_by_id = {str(team.id): team for team in teams}
        team_ids = {
            str(team.id)
            for team in teams
            if team.name.lower() in team_names
        }

        services = await service_repo.list_all()
        service_team_ids: dict[str, str] = {}
        for service in services:
            team = team_by_id.get(str(service.team_id))
            if team is None:
                continue
            if service.name.lower() in service_names:
                sid = str(service.id)
                tid = str(service.team_id)
                service_team_ids[sid] = tid
                team_ids.add(tid)
    finally:
        await service_repo.close()
        await team_repo.close()

    return {
        "team_ids": sorted(team_ids),
        "service_team_ids": service_team_ids,
    }


def _retrieval_update(
    state: dict[str, Any],
    chunks: list[Chunk],
    *,
    mode: str,
    retrieval_rounds: int,
    retrieval_result: AgentResult,
) -> dict[str, Any]:
    if mode == "discovery":
        return {
            "discovery_chunks": chunks,
            "retrieval_result": AgentResult(
                status=retrieval_result.status,
                data=retrieval_result.data,
                error=retrieval_result.error,
                degradation_note=retrieval_result.degradation_note,
            ),
            # Router consumes ``retrieved_chunks`` immediately after discovery.
            "retrieved_chunks": chunks,
            "retrieval_rounds": retrieval_rounds,
        }

    existing_value = (
        state.get("deep_dive_chunks")
        if "deep_dive_chunks" in state
        else state.get("retrieved_chunks")
    )
    existing = normalize_chunks(existing_value or [])
    merged = _merge_chunks(existing, chunks)
    update = {
        "deep_dive_chunks": merged,
        # Downstream specialist agents and final synthesis must use deep-dive
        # evidence, not the broad org-wide discovery set.
        "retrieved_chunks": merged,
        "retrieval_result": retrieval_result,
        "retrieval_rounds": retrieval_rounds,
    }
    if mode == "coverage_retry":
        update["coverage_retry_rounds"] = int(state.get("coverage_retry_rounds", 0) or 0) + 1
    return update


def _stamp_retrieval_pass(chunks: list[Chunk], pass_label: str) -> None:
    for chunk in chunks:
        chunk.retrieval_pass = pass_label


def _merge_chunks(existing: list[Chunk], new_chunks: list[Chunk]) -> list[Chunk]:
    merged: dict[str, Chunk] = {}
    order: list[str] = []

    for chunk in [*existing, *new_chunks]:
        key = chunk.canonical_chunk_id or chunk.chunk_id or chunk.metadata.source_path
        if key not in merged:
            merged[key] = chunk
            order.append(key)
            continue
        if chunk.score > merged[key].score:
            merged[key] = chunk

    return [merged[key] for key in order]
