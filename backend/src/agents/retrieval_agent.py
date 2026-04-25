from __future__ import annotations

from typing import Any

from src.agents.result import AgentResult
from src.agents.step_callbacks import get_step_callback
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.hybrid_search import HybridSearchEngine, RetrievalUnavailable

log = get_logger("retrieval_agent")

MIN_RELEVANT_CHUNKS = 3
MIN_RELEVANCE_SCORE = 0.3


async def retrieval_agent(state: dict[str, Any]) -> dict[str, Any]:
    requirement = state.get("search_query") or state["requirement"]
    analysis_id = state.get("analysis_id", "unknown")
    retrieval_rounds = state.get("retrieval_rounds", 0)
    on_step = get_step_callback(state.get("analysis_id"))

    log.info("retrieval_start", analysis_id=analysis_id, round=retrieval_rounds + 1)

    if on_step:
        await on_step(
            {
                "agent": "retrieve",
                "action": "searching",
                "detail": f"Round {retrieval_rounds + 1}: Expanding queries and searching...",
            }
        )

    # Pull declared scope from the analysis input so retrieval pushes down
    # ``org_id`` / ``team_ids`` / ``service_ids`` into OpenSearch. Without
    # this an analyze run could surface chunks from teams/services the user
    # never asked about. ``org_id`` falsy => no scope (legacy behavior).
    analysis_input = state.get("analysis_input") or {}
    scope_filter: dict | None = None
    org_id = analysis_input.get("org_id") if isinstance(analysis_input, dict) else None
    if org_id:
        scope_filter = {
            "org_id": org_id,
            "team_ids": analysis_input.get("team_ids") or [],
            "service_ids": analysis_input.get("service_ids") or [],
        }

    search_engine = HybridSearchEngine()
    try:
        chunks = await search_engine.search(
            requirement=requirement,
            expand=True,
            scope_filter=scope_filter,
        )
    except RetrievalUnavailable as e:
        # Infrastructure failure -- distinct from "found no relevant
        # docs". Falling through to the partial-results path would let
        # downstream agents synthesize an answer with zero evidence,
        # which is exactly the misleading-output case codex flagged.
        # Mark the agent ``failed`` so the orchestrator surfaces the
        # outage in the analysis status + SSE stream rather than
        # producing a confident-but-empty report.
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

    if on_step:
        await on_step(
            {
                "agent": "retrieve",
                "action": "results",
                "detail": f"Found {len(chunks)} chunks across documents",
                "data": {
                    "round": retrieval_rounds + 1,
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
        return {
            "retrieved_chunks": chunks,
            "retrieval_result": AgentResult(
                status="partial",
                degradation_note=(
                    f"Found only {len(relevant_chunks)} relevant documents (minimum: {MIN_RELEVANT_CHUNKS}). "
                    "This requirement may involve new capabilities not yet documented. "
                    "Analysis sections will be marked as low confidence."
                ),
            ),
            "retrieval_rounds": retrieval_rounds + 1,
        }

    if on_step:
        await on_step(
            {"agent": "retrieve", "action": "complete", "detail": f"{len(relevant_chunks)} relevant chunks from {len(chunks)} total"}
        )

    log.info(
        "retrieval_complete",
        analysis_id=analysis_id,
        total=len(chunks),
        relevant=len(relevant_chunks),
    )

    return {
        "retrieved_chunks": chunks,
        "retrieval_result": AgentResult(status="success"),
        "retrieval_rounds": retrieval_rounds + 1,
    }
