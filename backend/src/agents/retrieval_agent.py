from __future__ import annotations

from typing import Any

from src.agents.result import AgentResult
from src.agents.step_callbacks import get_step_callback
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.hybrid_search import HybridSearchEngine

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

    search_engine = HybridSearchEngine()
    chunks = await search_engine.search(
        requirement=requirement,
        expand=True,
    )

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
