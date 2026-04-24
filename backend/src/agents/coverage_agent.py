from __future__ import annotations

import json
from typing import Any

from src.agents.llm import llm_call
from src.agents.prompts import COVERAGE_SYSTEM_PROMPT, build_coverage_prompt
from src.agents.result import AgentResult
from src.agents.schemas import CoverageOutput
from src.agents.state_codec import normalize_agent_result, normalize_chunks
from src.agents.step_callbacks import get_step_callback
from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("coverage_agent")


async def coverage_agent(state: dict[str, Any]) -> dict[str, Any]:
    requirement = state.get("analysis_brief") or state["requirement"]
    chunks: list[Chunk] = normalize_chunks(state.get("retrieved_chunks", []))
    routing = normalize_agent_result(state.get("team_routing"))
    dependencies = normalize_agent_result(state.get("dependencies"))
    risk_assessment = normalize_agent_result(state.get("risk_assessment"))
    analysis_id = state.get("analysis_id", "unknown")
    on_step = get_step_callback(state.get("analysis_id"))

    log.info("coverage_start", analysis_id=analysis_id)

    if on_step:
        await on_step({"agent": "coverage", "action": "checking", "detail": "Verifying analysis coverage..."})

    analysis_summary = _build_analysis_summary(routing, dependencies, risk_assessment)
    platforms = _count_platforms(chunks)
    doc_stats = _build_doc_stats(chunks)

    try:
        prompt = build_coverage_prompt(
            requirement,
            analysis_summary,
            platforms,
            doc_stats,
            thread_transcript=state.get("thread_transcript") or "",
        )

        coverage = await llm_call(
            prompt=prompt,
            system_prompt=COVERAGE_SYSTEM_PROMPT,
            output_schema=CoverageOutput,
            model=settings.model_bulk,
            agent_name="coverage",
            analysis_id=analysis_id,
            on_step=on_step,
        )

        coverage.documents_retrieved = len(chunks)
        coverage.platforms_searched = list(set(c.metadata.source_platform for c in chunks))

        if on_step:
            try:
                await on_step(
                    {
                        "agent": "coverage",
                        "action": "results",
                        "detail": f"{coverage.documents_retrieved} docs, {len(coverage.gaps)} gaps ({len(coverage.critical_gaps)} critical)",
                        "data": {
                            "documents_retrieved": coverage.documents_retrieved,
                            "platforms": coverage.platforms_searched,
                            "gaps": coverage.gaps[:6],
                            "critical_gaps": coverage.critical_gaps[:4],
                            "needs_retry": len(coverage.critical_gaps) > 0,
                            "reasoning": coverage.reasoning or "",
                        },
                    }
                )
            except Exception as e:
                log.warning("coverage_results_step_failed", error=str(e))
            await on_step({"agent": "coverage", "action": "complete", "detail": "Coverage analysis complete"})

        log.info(
            "coverage_complete",
            analysis_id=analysis_id,
            gaps=len(coverage.gaps),
            critical_gaps=len(coverage.critical_gaps),
        )

        return {
            "coverage_report": AgentResult(status="success", data=coverage.model_dump()),
        }

    except Exception as e:
        log.error("coverage_failed", analysis_id=analysis_id, error=str(e))
        if on_step:
            await on_step({"agent": "coverage", "action": "failed", "detail": str(e)[:200]})
        return {
            "coverage_report": AgentResult(
                status="partial",
                data=CoverageOutput(
                    documents_retrieved=len(chunks),
                    platforms_searched=list(set(c.metadata.source_platform for c in chunks)),
                    gaps=[f"Coverage analysis failed: {str(e)}"],
                ).model_dump(),
                error=str(e),
            ),
        }


def _build_analysis_summary(routing, dependencies, risk_assessment) -> str:
    parts = []

    if routing and routing.data:
        data = routing.data if isinstance(routing.data, dict) else {}
        primary = data.get("primary_team", {})
        if primary:
            parts.append(f"Primary team: {primary.get('name', 'unknown')}")
        services = data.get("affected_services", [])
        if services:
            svc_names = [s.get("name", "") for s in services if isinstance(s, dict)]
            parts.append(f"Affected services: {', '.join(svc_names)}")

    if dependencies and dependencies.data:
        data = dependencies.data if isinstance(dependencies.data, dict) else {}
        blocking = data.get("blocking", [])
        if blocking:
            parts.append(f"Blocking dependencies: {len(blocking)}")

    if risk_assessment and risk_assessment.data:
        data = risk_assessment.data if isinstance(risk_assessment.data, dict) else {}
        parts.append(f"Overall risk: {data.get('overall_risk', 'unknown')}")

    return "\n".join(parts) if parts else "No analysis data available"


def _count_platforms(chunks: list[Chunk]) -> str:
    platform_counts: dict[str, int] = {}
    for chunk in chunks:
        p = chunk.metadata.source_platform
        platform_counts[p] = platform_counts.get(p, 0) + 1
    return json.dumps(platform_counts)


def _build_doc_stats(chunks: list[Chunk]) -> str:
    doc_types: dict[str, int] = {}
    for chunk in chunks:
        dt = chunk.metadata.doc_type
        doc_types[dt] = doc_types.get(dt, 0) + 1

    unique_docs = len(set(c.document_id for c in chunks))
    return f"Total chunks: {len(chunks)}, Unique documents: {unique_docs}, Types: {json.dumps(doc_types)}"
