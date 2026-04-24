from __future__ import annotations

import json
from typing import Any

from src.agents.llm import llm_call
from src.agents.prompts import DEPENDENCY_SYSTEM_PROMPT, build_dependency_prompt
from src.agents.result import AgentResult
from src.agents.schemas import DependencyOutput
from src.agents.state_codec import normalize_agent_result, normalize_chunks
from src.agents.step_callbacks import get_step_callback
from src.catalog import ServiceRepository
from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.knowledge_queries import find_related_services
from src.retrieval.reranker import rerank_for_agent

log = get_logger("dependency_agent")


async def dependency_agent(state: dict[str, Any]) -> dict[str, Any]:
    requirement = state.get("analysis_brief") or state["requirement"]
    chunks: list[Chunk] = normalize_chunks(state.get("retrieved_chunks", []))
    routing_data = normalize_agent_result(state.get("team_routing"))
    analysis_id = state.get("analysis_id", "unknown")
    on_step = get_step_callback(state.get("analysis_id"))

    log.info("dependency_start", analysis_id=analysis_id)

    if on_step:
        await on_step({"agent": "deps", "action": "analyzing", "detail": "Mapping service dependencies..."})

    ranked_chunks = rerank_for_agent(chunks, requirement, "dependency")

    service_names = _extract_service_names(routing_data, chunks)

    try:
        service_repo = await ServiceRepository.create()

        if on_step:
            await on_step(
                {
                    "agent": "deps",
                    "action": "traversing",
                    "detail": f"Traversing dependency graph for {len(service_names)} services...",
                    "data": {"services": len(service_names)},
                }
            )

        deps_map = await find_related_services(service_repo, service_names, depth=2)
        await service_repo.close()

        chunks_text = _format_chunks(ranked_chunks)
        graph_deps = json.dumps(deps_map, indent=2, default=str)
        services_text = ", ".join(service_names) if service_names else "None identified"

        prompt = build_dependency_prompt(
            requirement,
            chunks_text,
            graph_deps,
            services_text,
            thread_transcript=state.get("thread_transcript") or "",
        )

        dep_output = await llm_call(
            prompt=prompt,
            system_prompt=DEPENDENCY_SYSTEM_PROMPT,
            output_schema=DependencyOutput,
            model=settings.model_bulk,
            agent_name="deps",
            analysis_id=analysis_id,
            on_step=on_step,
        )

        if on_step:
            try:
                blocking_pairs = [f"{d.from_service} -> {d.to_service}" for d in dep_output.blocking[:5]]
                impacted_pairs = [f"{d.from_service} -> {d.to_service}" for d in dep_output.impacted[:5]]
                await on_step(
                    {
                        "agent": "deps",
                        "action": "results",
                        "detail": f"{len(dep_output.blocking)} blocking, {len(dep_output.impacted)} impacted, {len(dep_output.informational)} informational",
                        "data": {
                            "blocking": blocking_pairs,
                            "impacted": impacted_pairs,
                            "informational_count": len(dep_output.informational),
                            "reasoning": dep_output.reasoning or "",
                        },
                    }
                )
            except Exception as e:
                log.warning("deps_results_step_failed", error=str(e))
            await on_step({"agent": "deps", "action": "complete", "detail": "Dependency analysis complete"})

        log.info(
            "dependency_complete",
            analysis_id=analysis_id,
            blocking=len(dep_output.blocking),
            impacted=len(dep_output.impacted),
        )

        return {
            "dependencies": AgentResult(status="success", data=dep_output.model_dump()),
        }

    except Exception as e:
        log.error("dependency_failed", analysis_id=analysis_id, error=str(e))
        if on_step:
            await on_step({"agent": "deps", "action": "failed", "detail": str(e)[:200]})
        return {
            "dependencies": AgentResult(status="failed", error=str(e)),
        }


def _extract_service_names(routing_data: AgentResult | None, chunks: list[Chunk]) -> list[str]:
    services = set()

    routed_services_found = False
    if routing_data and routing_data.data:
        data = routing_data.data if isinstance(routing_data.data, dict) else routing_data.data
        for svc in data.get("affected_services", []):
            name = svc.get("name", "") if isinstance(svc, dict) else ""
            if name:
                services.add(name)
                routed_services_found = True

    # Prefer the router's explicit in-scope services. Fall back to chunk hints
    # only when routing did not identify any services.
    if not routed_services_found:
        for chunk in chunks:
            if chunk.metadata.service_hint:
                services.add(chunk.metadata.service_hint)

    return list(services)


def _format_chunks(chunks: list[Chunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Doc {i}] {chunk.metadata.source_path}\nContent:\n{chunk.content[:800]}\n")
    return "\n---\n".join(parts)
