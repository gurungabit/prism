from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.llm import llm_call
from src.agents.prompts import RISK_EFFORT_SYSTEM_PROMPT, build_risk_effort_prompt
from src.agents.result import AgentResult
from src.agents.schemas import RiskEffortOutput
from src.agents.state_codec import normalize_agent_result, normalize_chunks
from src.agents.step_callbacks import get_step_callback
from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.reranker import rerank_for_agent

log = get_logger("risk_effort_agent")


async def risk_effort_agent(state: dict[str, Any]) -> dict[str, Any]:
    requirement = state.get("analysis_brief") or state["requirement"]
    chunks: list[Chunk] = normalize_chunks(state.get("retrieved_chunks", []))
    routing_data = normalize_agent_result(state.get("team_routing"))
    analysis_id = state.get("analysis_id", "unknown")
    on_step = get_step_callback(state.get("analysis_id"))

    log.info("risk_effort_start", analysis_id=analysis_id)

    if on_step:
        await on_step(
            {"agent": "risk", "action": "analyzing", "detail": "Assessing risks and estimating effort..."}
        )

    ranked_chunks = rerank_for_agent(chunks, requirement, "risk")

    services_text = _extract_services_text(routing_data)
    teams_text = _extract_teams_text(routing_data)
    chunks_text = _format_chunks(ranked_chunks)

    try:
        prompt = build_risk_effort_prompt(requirement, chunks_text, services_text, teams_text)

        risk_output = await llm_call(
            prompt=prompt,
            system_prompt=RISK_EFFORT_SYSTEM_PROMPT,
            output_schema=RiskEffortOutput,
            model=settings.model_risk,
            agent_name="risk",
            analysis_id=analysis_id,
            on_step=on_step,
        )

        # Compute totals from breakdown if LLM left them at 0
        if risk_output.effort_breakdown and risk_output.total_days_min == 0 and risk_output.total_days_max == 0:
            risk_output.total_days_min = sum(e.days_min for e in risk_output.effort_breakdown)
            risk_output.total_days_max = sum(e.days_max for e in risk_output.effort_breakdown)

        stale_sources = _detect_stale_sources(ranked_chunks)

        if on_step:
            try:
                risk_items = [f"[{r.level}] {r.description}" for r in risk_output.risks[:6]]
                effort_items = [f"{e.task} ({e.days_min}-{e.days_max}d)" for e in risk_output.effort_breakdown[:6]]
                await on_step(
                    {
                        "agent": "risk",
                        "action": "results",
                        "detail": f"Risk: {risk_output.overall_risk} | Effort: {risk_output.total_days_min}-{risk_output.total_days_max} days",
                        "data": {
                            "overall_risk": risk_output.overall_risk,
                            "risks": risk_items,
                            "effort_range": f"{risk_output.total_days_min}-{risk_output.total_days_max} days",
                            "effort_breakdown": effort_items,
                            "staffing": f"{risk_output.staffing_engineers} engineers, {risk_output.staffing_reviewers} reviewers",
                            "calendar": f"{risk_output.calendar_weeks_min}-{risk_output.calendar_weeks_max} weeks",
                            "reasoning": risk_output.reasoning or "",
                        },
                    }
                )
            except Exception as e:
                log.warning("risk_results_step_failed", error=str(e))
            await on_step({"agent": "risk", "action": "complete", "detail": "Risk assessment complete"})

        log.info(
            "risk_effort_complete",
            analysis_id=analysis_id,
            overall_risk=risk_output.overall_risk,
            risk_count=len(risk_output.risks),
            days_range=f"{risk_output.total_days_min}-{risk_output.total_days_max}",
        )

        return {
            "risk_assessment": AgentResult(status="success", data=risk_output.model_dump()),
            "stale_sources": stale_sources,
        }

    except Exception as e:
        log.error("risk_effort_failed", analysis_id=analysis_id, error=str(e))
        if on_step:
            await on_step({"agent": "risk", "action": "failed", "detail": str(e)[:200]})
        return {
            "risk_assessment": AgentResult(status="failed", error=str(e)),
            "stale_sources": [],
        }


def _extract_services_text(routing_data: AgentResult | None) -> str:
    if not routing_data or not routing_data.data:
        return "No services identified"
    data = routing_data.data if isinstance(routing_data.data, dict) else {}
    services = data.get("affected_services", [])
    return json.dumps(services, indent=2) if services else "No services identified"


def _extract_teams_text(routing_data: AgentResult | None) -> str:
    if not routing_data or not routing_data.data:
        return "No teams identified"
    data = routing_data.data if isinstance(routing_data.data, dict) else {}
    primary = data.get("primary_team", {})
    return json.dumps([primary], indent=2) if primary else "No teams identified"


def _detect_stale_sources(chunks: list[Chunk]) -> list[str]:
    stale = []
    threshold = datetime.now(UTC) - timedelta(days=settings.staleness_threshold_days)

    for chunk in chunks:
        last_modified = _normalize_datetime(chunk.metadata.last_modified)
        if last_modified and last_modified < threshold:
            stale.append(
                f"{chunk.metadata.source_path} (last updated: {last_modified.strftime('%Y-%m-%d')})"
            )

    return list(set(stale))


def _format_chunks(chunks: list[Chunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        last_modified = _normalize_datetime(chunk.metadata.last_modified)
        modified = last_modified.strftime("%Y-%m-%d") if last_modified else "unknown"
        parts.append(
            f"[Doc {i}] {chunk.metadata.source_path} (modified: {modified})\n"
            f"Type: {chunk.metadata.doc_type}\n"
            f"Content:\n{chunk.content[:800]}\n"
        )
    return "\n---\n".join(parts)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
