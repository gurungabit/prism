from __future__ import annotations

import json
from typing import Any

from src.agents.llm import llm_call
from src.agents.prompts import ROUTER_SYSTEM_PROMPT, build_router_prompt
from src.agents.result import AgentResult
from src.agents.schemas import RouterOutput
from src.agents.state_codec import normalize_chunks
from src.agents.step_callbacks import get_step_callback
from src.catalog import ServiceRepository, TeamRepository
from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.knowledge_queries import get_all_teams
from src.retrieval.reranker import rerank_for_agent

log = get_logger("router_agent")


async def router_agent(state: dict[str, Any]) -> dict[str, Any]:
    requirement = state.get("analysis_brief") or state["requirement"]
    chunks: list[Chunk] = normalize_chunks(state.get("retrieved_chunks", []))
    analysis_id = state.get("analysis_id", "unknown")
    on_step = get_step_callback(state.get("analysis_id"))

    log.info("router_start", analysis_id=analysis_id)

    if on_step:
        await on_step({"agent": "route", "action": "reranking", "detail": "Filtering documents for team routing..."})

    ranked_chunks = rerank_for_agent(chunks, requirement, "router")

    try:
        # Catalog-backed team list. Under the declared model ownership is a
        # direct lookup (no inference, no conflict surface -- see plan open
        # question 4), so we pass an empty ``conflicts`` to keep the prompt
        # contract stable without misleading the router.
        team_repo = await TeamRepository.create()
        service_repo = await ServiceRepository.create()

        if on_step:
            await on_step(
                {
                    "agent": "route",
                    "action": "querying_graph",
                    "detail": "Querying declared catalog for teams and services...",
                }
            )

        teams = await get_all_teams(team_repo, service_repo)
        conflicts: list[dict] = []

        chunks_text = _format_chunks(ranked_chunks)
        graph_data = json.dumps(teams, indent=2, default=str)
        conflicts_text = "None detected"

        prompt = build_router_prompt(requirement, chunks_text, graph_data, conflicts_text)

        if on_step:
            await on_step(
                {"agent": "route", "action": "scoring", "detail": f"Scoring {len(teams)} candidate teams...", "data": {"candidates": len(teams)}}
            )

        routing = await llm_call(
            prompt=prompt,
            system_prompt=ROUTER_SYSTEM_PROMPT,
            output_schema=RouterOutput,
            model=settings.model_router,
            agent_name="route",
            analysis_id=analysis_id,
            on_step=on_step,
        )

        await team_repo.close()
        await service_repo.close()

        if on_step:
            try:
                services_found = [s.name for s in routing.affected_services[:8]]
                conf = routing.primary_team.confidence
                conf_pct = f"{conf:.0%}" if conf <= 1.0 else f"{conf:.0f}%"
                await on_step(
                    {
                        "agent": "route",
                        "action": "results",
                        "detail": f"Primary: {routing.primary_team.name} ({conf_pct} confidence)",
                        "data": {
                            "primary_team": routing.primary_team.name,
                            "confidence": conf_pct,
                            "affected_services": services_found,
                            "reasoning": routing.reasoning or "",
                        },
                    }
                )
            except Exception as e:
                log.warning("route_results_step_failed", error=str(e))
            await on_step({"agent": "route", "action": "complete", "detail": "Team routing complete"})

        log.info(
            "router_complete",
            analysis_id=analysis_id,
            primary_team=routing.primary_team.name,
            confidence=routing.primary_team.confidence,
        )

        return {
            "team_routing": AgentResult(status="success", data=routing.model_dump()),
            # Conflicts retained in the state shape to avoid churning every
            # downstream consumer, but always empty under the declared model.
            "conflicts": [],
        }

    except Exception as e:
        log.error("router_failed", analysis_id=analysis_id, error=str(e))
        if on_step:
            await on_step({"agent": "route", "action": "failed", "detail": str(e)[:200]})
        return {
            "team_routing": AgentResult(status="failed", error=str(e)),
            "conflicts": [],
        }


def _format_chunks(chunks: list[Chunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[Doc {i}] Source: {chunk.metadata.source_path}\n"
            f"Title: {chunk.metadata.document_title}\n"
            f"Section: {chunk.metadata.section_heading}\n"
            f"Type: {chunk.metadata.doc_type}\n"
            f"Modified: {chunk.metadata.last_modified}\n"
            f"Content:\n{chunk.content[:1000]}\n"
        )
    return "\n---\n".join(parts)
