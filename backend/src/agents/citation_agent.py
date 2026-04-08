from __future__ import annotations

import json
from typing import Any

from src.agents.llm import llm_call
from src.agents.prompts import CITATION_SYSTEM_PROMPT, build_citation_prompt
from src.agents.result import AgentResult
from src.agents.schemas import CitationVerification
from src.agents.state_codec import normalize_agent_result, normalize_chunks
from src.agents.step_callbacks import get_step_callback
from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("citation_agent")


async def citation_agent(state: dict[str, Any]) -> dict[str, Any]:
    requirement = state.get("analysis_brief") or state["requirement"]
    chunks: list[Chunk] = normalize_chunks(state.get("retrieved_chunks", []))
    routing = normalize_agent_result(state.get("team_routing"))
    dependencies = normalize_agent_result(state.get("dependencies"))
    risk_assessment = normalize_agent_result(state.get("risk_assessment"))
    analysis_id = state.get("analysis_id", "unknown")
    on_step = get_step_callback(state.get("analysis_id"))

    log.info("citation_start", analysis_id=analysis_id)

    if on_step:
        await on_step({"agent": "citation", "action": "verifying", "detail": "Validating citations and references..."})

    analysis_text = _compile_analysis_text(routing, dependencies, risk_assessment)
    sources_text = _format_sources(chunks)

    try:
        prompt = build_citation_prompt(analysis_text, sources_text)

        verification = await llm_call(
            prompt=prompt,
            system_prompt=CITATION_SYSTEM_PROMPT,
            output_schema=CitationVerification,
            model=settings.model_bulk,
            agent_name="citation",
            analysis_id=analysis_id,
            on_step=on_step,
        )

        if on_step:
            try:
                verified_items = [f"{c.claim[:80]}... ({c.confidence})" for c in verification.verified_claims[:6]]
                await on_step(
                    {
                        "agent": "citation",
                        "action": "results",
                        "detail": f"{len(verification.verified_claims)} verified, {len(verification.unsupported_claims)} unsupported",
                        "data": {
                            "verified_claims": verified_items,
                            "unsupported_claims": verification.unsupported_claims[:4],
                            "stale_warnings": verification.stale_source_warnings[:4],
                        },
                    }
                )
            except Exception as e:
                log.warning("citation_results_step_failed", error=str(e))
            await on_step({"agent": "citation", "action": "complete", "detail": "Citation verification complete"})

        log.info(
            "citation_complete",
            analysis_id=analysis_id,
            verified=len(verification.verified_claims),
            unsupported=len(verification.unsupported_claims),
        )

        return {
            "citation_result": AgentResult(status="success", data=verification.model_dump()),
        }

    except Exception as e:
        log.error("citation_failed", analysis_id=analysis_id, error=str(e))
        if on_step:
            await on_step({"agent": "citation", "action": "failed", "detail": str(e)[:200]})
        return {
            "citation_result": AgentResult(
                status="partial",
                error=str(e),
                degradation_note="Citation verification failed. Claims may lack source validation.",
            ),
        }


def _compile_analysis_text(routing, dependencies, risk_assessment) -> str:
    parts = []

    if routing and routing.data:
        parts.append(f"ROUTING:\n{json.dumps(routing.data, indent=2, default=str)}")

    if dependencies and dependencies.data:
        parts.append(f"DEPENDENCIES:\n{json.dumps(dependencies.data, indent=2, default=str)}")

    if risk_assessment and risk_assessment.data:
        parts.append(f"RISK & EFFORT:\n{json.dumps(risk_assessment.data, indent=2, default=str)}")

    return "\n\n".join(parts) if parts else "No analysis data"


def _format_sources(chunks: list[Chunk]) -> str:
    seen_paths = set()
    parts = []
    for chunk in chunks:
        path = chunk.metadata.source_path
        if path in seen_paths:
            continue
        seen_paths.add(path)

        modified = chunk.metadata.last_modified.strftime("%Y-%m-%d") if chunk.metadata.last_modified else "unknown"
        parts.append(
            f"- {path} (platform: {chunk.metadata.source_platform}, "
            f"type: {chunk.metadata.doc_type}, modified: {modified})"
        )

    return "\n".join(parts) if parts else "No source documents available"
