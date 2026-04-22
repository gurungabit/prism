from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from src.agents.citation_agent import citation_agent
from src.agents.coverage_agent import coverage_agent
from src.agents.dependency_agent import dependency_agent
from src.agents.llm import llm_call
from src.agents.prompts import (
    CHAT_ANSWER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    ROLLING_SUMMARY_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    build_chat_answer_prompt,
    build_rolling_summary_prompt,
    build_synthesis_prompt,
)
from src.agents.result import AgentResult
from src.agents.retrieval_agent import retrieval_agent
from src.agents.risk_effort_agent import risk_effort_agent
from src.agents.router_agent import router_agent
from src.agents.schemas import (
    ChatAnswerOutput,
    PlanOutput,
    RollingSummaryOutput,
    SynthesisOutput,
)
from src.agents.state_codec import checkpoint_safe_update, normalize_chunks
from src.agents.step_callbacks import clear_step_callback, get_step_callback, register_step_callback
from src.config import settings
from src.models.report import (
    AnalysisInput,
    AffectedService,
    Citation,
    ConflictClaimant,
    CoverageReport,
    DependencyEdge,
    DependencyTree,
    EffortBreakdown,
    EffortEstimate,
    ImpactMatrixRow,
    OwnershipConflict,
    PRISMReport,
    RiskAssessment,
    RiskItem,
    SourceDocument,
    StaffingEstimate,
    TeamCandidate,
    TeamRouting,
    VerificationReport,
    VerifiedClaim,
    build_analysis_brief,
    build_search_query,
)
from src.observability.logging import get_logger

log = get_logger("orchestrator")

_compiled_app = None
_compiled_app_has_checkpointer = False
_compiled_app_lock: asyncio.Lock | None = None
_checkpointer_stack: AsyncExitStack | None = None


def _get_compiled_app_lock() -> asyncio.Lock:
    global _compiled_app_lock
    if _compiled_app_lock is None:
        _compiled_app_lock = asyncio.Lock()
    return _compiled_app_lock


class OrchestratorState(TypedDict):
    requirement: str
    analysis_id: str
    analysis_input: dict | None
    analysis_brief: str
    search_query: str
    retrieved_chunks: list
    # Planner decision -- which downstream agents to run. Keys mirror
    # ``PlanOutput.agents_to_run``. Empty/missing means "run all" for
    # backwards compatibility with callers that don't hit the planner.
    plan: dict | None
    # Thread context seeded from prior runs on follow-ups. Each entry:
    # {requirement, kind, rolling_summary, report, retrieved_chunks}.
    # Empty list for first-turn runs.
    prior_turns: list
    team_routing: AgentResult | None
    dependencies: AgentResult | None
    risk_assessment: AgentResult | None
    coverage_report: AgentResult | None
    citation_result: AgentResult | None
    stale_sources: list
    conflicts: list
    retrieval_rounds: int
    agent_trace: list
    final_report: dict | None
    # Chat-mode runs populate this instead of final_report.
    chat_answer: dict | None


def _result_data(result: AgentResult | dict | None) -> dict:
    if not result:
        return {}
    if isinstance(result, dict):
        data = result.get("data", {})
        return data if isinstance(data, dict) else {}
    data = result.data
    return data if isinstance(data, dict) else {}


_ALL_AGENTS: list[str] = ["router", "dependencies", "risk_effort", "coverage"]


def _format_thread_context(prior_turns: list) -> str:
    """Render the thread's prior turns as a compact transcript for the
    planner / chat-mode prompts. Uses rolling_summary for older turns when
    available; falls back to the turn's exec summary or chat answer.
    """
    if not prior_turns:
        return ""
    lines: list[str] = []
    for i, turn in enumerate(prior_turns, start=1):
        req = (turn.get("requirement") or "").strip()
        summary = (turn.get("rolling_summary") or "").strip()
        if not summary:
            report = turn.get("report") or {}
            summary = (report.get("executive_summary") or "").strip()
        if not summary:
            answer = (turn.get("chat_answer") or {}).get("answer", "").strip()
            summary = answer
        kind = turn.get("kind", "full")
        lines.append(f"Turn {i} [{kind}]: {req}\n  -> {summary or '(no summary)'}")
    return "\n\n".join(lines)


async def plan_node(state: OrchestratorState) -> dict:
    analysis_id = state["analysis_id"]
    on_step = get_step_callback(analysis_id)
    requirement = state["requirement"]
    prior_turns = state.get("prior_turns") or []
    log.info(
        "plan_start",
        analysis_id=analysis_id,
        requirement=requirement[:100],
        prior_turn_count=len(prior_turns),
    )

    if on_step:
        await on_step(
            {
                "agent": "plan",
                "action": "planning",
                "detail": "Picking which agents to run...",
            }
        )

    # Default fallback -- if the LLM call fails we run the full pipeline so
    # analysis quality degrades gracefully instead of silently skipping
    # agents.
    plan_dict: dict = {
        "mode": "full",
        "question_type": "general",
        "agents_to_run": list(_ALL_AGENTS),
        "reasoning": "Planner fallback (LLM unavailable) -- running all agents.",
    }

    transcript = _format_thread_context(prior_turns)
    user_prompt = (
        f"Requirement:\n{requirement}\n\n"
        + (f"Prior thread context:\n{transcript}\n\n" if transcript else "(No prior thread context — this is the first turn.)\n\n")
        + "Decide the mode and which agents to run."
    )

    try:
        plan = await llm_call(
            prompt=user_prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            output_schema=PlanOutput,
            model=settings.model_router,
            agent_name="plan",
            analysis_id=analysis_id,
        )
        # First turn can never be chat-mode -- there's no prior context to
        # answer from. Force full to avoid the LLM mis-classifying an initial
        # requirement as a follow-up.
        mode = plan.mode if prior_turns else "full"

        if mode == "chat":
            agents: list[str] = []
        else:
            # Router is load-bearing for synthesis -- it emits primary_team,
            # which drives the exec summary. Force it in unless the planner
            # explicitly asked for coverage-only.
            agents = list(dict.fromkeys(plan.agents_to_run))
            if not agents:
                agents = ["router"]
            elif "router" not in agents and plan.question_type != "coverage":
                agents = ["router"] + agents
        plan_dict = {
            "mode": mode,
            "question_type": plan.question_type,
            "agents_to_run": agents,
            "reasoning": plan.reasoning,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("plan_llm_failed", analysis_id=analysis_id, error=str(e))

    skipped = [a for a in _ALL_AGENTS if a not in plan_dict["agents_to_run"]]
    log.info(
        "plan_complete",
        analysis_id=analysis_id,
        mode=plan_dict["mode"],
        question_type=plan_dict["question_type"],
        agents_to_run=plan_dict["agents_to_run"],
        skipped=skipped,
    )

    if on_step:
        if plan_dict["mode"] == "chat":
            detail = f"[chat] {plan_dict['reasoning'][:80]}"
        else:
            agents_label = ", ".join(plan_dict["agents_to_run"])
            detail = f"[{plan_dict['question_type']}] running: {agents_label}"
        await on_step(
            {
                "agent": "plan",
                "action": "results",
                "detail": detail,
                "data": plan_dict,
            }
        )
        await on_step(
            {
                "agent": "plan",
                "action": "complete",
                "detail": "Analysis plan ready",
            }
        )

    return checkpoint_safe_update(
        {
            "plan": plan_dict,
            "agent_trace": [
                {
                    "agent": "orchestrator",
                    "action": "plan",
                    "timestamp": time.time(),
                    "data": plan_dict,
                }
            ],
        }
    )


def _agent_enabled(state: OrchestratorState, key: str) -> bool:
    """Return True if the planner asked for this agent (or didn't plan).

    Chat-mode plans don't route through agent nodes, but if they ever do
    (e.g. a future edit adds them back into the graph), they're always
    disabled.
    """
    plan = state.get("plan")
    if not plan:
        return True
    if isinstance(plan, dict) and plan.get("mode") == "chat":
        return False
    agents = plan.get("agents_to_run") if isinstance(plan, dict) else None
    if agents is None:
        return True
    if not agents:
        return False
    return key in agents


async def _emit_skipped(analysis_id: str, agent: str, reason: str) -> None:
    on_step = get_step_callback(analysis_id)
    if on_step:
        await on_step(
            {
                "agent": agent,
                "action": "skipped",
                "detail": reason,
            }
        )
        await on_step(
            {
                "agent": agent,
                "action": "complete",
                "detail": "Skipped by planner",
            }
        )


async def retrieve_node(state: OrchestratorState) -> dict:
    return checkpoint_safe_update(await retrieval_agent(state))


async def chat_node(state: OrchestratorState) -> dict:
    """Short-answer path for chat-mode follow-ups.

    No retrieval, no agents -- we answer purely from the prior-turn context
    plus whatever chunks were already attached to the thread. Output shape:
    ``state["chat_answer"] = {"answer": str, "cited_paths": [...]}``.
    """
    analysis_id = state["analysis_id"]
    on_step = get_step_callback(analysis_id)
    prior_turns = state.get("prior_turns") or []

    if on_step:
        await on_step(
            {
                "agent": "chat",
                "action": "answering",
                "detail": "Answering from prior context...",
            }
        )

    # Roll every prior turn's retrieved chunks forward into this turn so we
    # can cite them without re-running retrieval. The newest turn's chunks
    # win on path collisions (most recent last_modified + score).
    merged_chunks: list = []
    seen_paths: set[str] = set()
    for turn in reversed(prior_turns):  # newest first so we prefer its chunks
        for ch in turn.get("retrieved_chunks") or []:
            # chunks may be AgentResult.data, dicts, or Chunk objects depending
            # on how the parent was serialized.
            path = ""
            if isinstance(ch, dict):
                metadata = ch.get("metadata") or {}
                path = metadata.get("source_path", "")
            else:
                path = getattr(getattr(ch, "metadata", None), "source_path", "")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            merged_chunks.append(ch)

    chunks_text = _chunks_for_chat_prompt(merged_chunks)
    transcript = _format_thread_context(prior_turns)

    default_answer = {
        "answer": "I couldn't reach the language model just now. Try re-asking.",
        "cited_paths": [],
    }

    try:
        result = await llm_call(
            prompt=build_chat_answer_prompt(
                requirement=state["requirement"],
                thread_transcript=transcript or "(no prior turns)",
                chunks_text=chunks_text,
            ),
            system_prompt=CHAT_ANSWER_SYSTEM_PROMPT,
            output_schema=ChatAnswerOutput,
            model=settings.model_synthesis,
            agent_name="chat",
            analysis_id=analysis_id,
            on_step=on_step,
        )
        answer_dict = {"answer": result.answer, "cited_paths": result.cited_paths}
    except Exception as e:  # noqa: BLE001
        log.error("chat_answer_failed", analysis_id=analysis_id, error=str(e))
        answer_dict = default_answer

    if on_step:
        await on_step(
            {
                "agent": "chat",
                "action": "results",
                "detail": answer_dict["answer"][:160],
                "data": answer_dict,
            }
        )
        await on_step(
            {
                "agent": "chat",
                "action": "complete",
                "detail": "Follow-up answered",
            }
        )

    return checkpoint_safe_update({"chat_answer": answer_dict})


def _chunks_for_chat_prompt(chunks: list, max_chars: int = 12000) -> str:
    """Flatten merged thread chunks into the chat prompt body. Truncates to
    avoid blowing the context window on long threads."""
    if not chunks:
        return "(no prior chunks)"
    parts: list[str] = []
    total = 0
    for i, ch in enumerate(chunks, start=1):
        if isinstance(ch, dict):
            metadata = ch.get("metadata") or {}
            path = metadata.get("source_path", "")
            content = ch.get("content") or ""
        else:
            path = getattr(getattr(ch, "metadata", None), "source_path", "")
            content = getattr(ch, "content", "") or ""
        snippet = f"[Doc {i}] {path}\n{content[:800]}"
        if total + len(snippet) > max_chars:
            break
        parts.append(snippet)
        total += len(snippet)
    return "\n\n".join(parts)


def route_after_plan(state: OrchestratorState) -> str:
    """Branch after the planner: chat-mode skips retrieval and all agents."""
    plan = state.get("plan") or {}
    return "chat" if plan.get("mode") == "chat" else "retrieve"


async def route_node(state: OrchestratorState) -> dict:
    if not _agent_enabled(state, "router"):
        await _emit_skipped(state["analysis_id"], "router", "Planner skipped routing")
        return {}
    return checkpoint_safe_update(await router_agent(state))


async def deps_node(state: OrchestratorState) -> dict:
    if not _agent_enabled(state, "dependencies"):
        await _emit_skipped(state["analysis_id"], "dependencies", "Planner skipped dependencies")
        return {}
    return checkpoint_safe_update(await dependency_agent(state))


async def risk_node(state: OrchestratorState) -> dict:
    if not _agent_enabled(state, "risk_effort"):
        await _emit_skipped(state["analysis_id"], "risk_effort", "Planner skipped risk/effort")
        return {}
    return checkpoint_safe_update(await risk_effort_agent(state))


async def coverage_node(state: OrchestratorState) -> dict:
    if not _agent_enabled(state, "coverage"):
        await _emit_skipped(state["analysis_id"], "coverage", "Planner skipped coverage")
        return {}
    return checkpoint_safe_update(await coverage_agent(state))


async def citation_node(state: OrchestratorState) -> dict:
    return checkpoint_safe_update(await citation_agent(state))


def should_retrieve_more(state: OrchestratorState) -> str:
    if state.get("retrieval_rounds", 0) >= settings.max_retrieval_rounds:
        return "citations"

    coverage = state.get("coverage_report")
    if not coverage:
        return "citations"

    # Handle both AgentResult objects and dicts (from checkpointer serialization)
    if isinstance(coverage, dict):
        cov_data = coverage.get("data", {})
    else:
        cov_data = coverage.data

    if isinstance(cov_data, dict):
        critical_gaps = cov_data.get("critical_gaps", [])
        if critical_gaps:
            log.info("coverage_gap_detected", gaps=len(critical_gaps), round=state.get("retrieval_rounds", 0))
            return "retrieve"

    return "citations"


async def synthesize_node(state: OrchestratorState) -> dict:
    analysis_id = state["analysis_id"]
    on_step = get_step_callback(analysis_id)

    log.info("synthesis_start", analysis_id=analysis_id)

    if on_step:
        await on_step({"agent": "synthesize", "action": "synthesizing", "detail": "Building final report..."})

    routing = state.get("team_routing")
    dependencies = state.get("dependencies")
    risk_assessment = state.get("risk_assessment")
    coverage = state.get("coverage_report")
    citations = state.get("citation_result")
    conflicts = state.get("conflicts", [])
    stale = state.get("stale_sources", [])
    chunks = normalize_chunks(state.get("retrieved_chunks", []))

    try:
        prompt = build_synthesis_prompt(
            requirement=state.get("analysis_brief", state["requirement"]),
            routing=json.dumps(_result_data(routing), default=str),
            dependencies=json.dumps(_result_data(dependencies), default=str),
            risks=json.dumps(_result_data(risk_assessment), default=str),
            coverage=json.dumps(_result_data(coverage), default=str),
            citations=json.dumps(_result_data(citations), default=str),
            conflicts=json.dumps(conflicts, default=str),
        )

        synthesis = await llm_call(
            prompt=prompt,
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            output_schema=SynthesisOutput,
            model=settings.model_synthesis,
            agent_name="synthesize",
            analysis_id=analysis_id,
            on_step=on_step,
        )
    except Exception as e:
        log.error("synthesis_failed", analysis_id=analysis_id, error=str(e))
        synthesis = None

    report = _build_report(
        state=state,
        synthesis=synthesis,
        routing=routing,
        dependencies=dependencies,
        risk_assessment=risk_assessment,
        coverage=coverage,
        citation_result=citations,
        conflicts=conflicts,
        stale_sources=stale,
        chunks=chunks,
    )

    if on_step:
        await on_step(
            {
                "agent": "synthesize",
                "action": "results",
                "detail": report.executive_summary[:160] or "Final report ready",
                "data": {
                    "executive_summary": report.executive_summary,
                    "recommendations": report.recommendations[:5],
                    "caveats": report.caveats[:4],
                    "data_quality_summary": report.data_quality_summary,
                },
            }
        )
        await on_step({"agent": "synthesize", "action": "complete", "detail": "Final report complete"})

    log.info("synthesis_complete", analysis_id=analysis_id)

    return checkpoint_safe_update(
        {
            "final_report": report.model_dump(mode="json"),
        }
    )


def _build_report(
    state: OrchestratorState,
    synthesis: SynthesisOutput | None,
    routing: AgentResult | None,
    dependencies: AgentResult | None,
    risk_assessment: AgentResult | None,
    coverage: AgentResult | None,
    citation_result: AgentResult | None,
    conflicts: list,
    stale_sources: list,
    chunks: list,
) -> PRISMReport:
    analysis_input_data = state.get("analysis_input")
    if analysis_input_data:
        analysis_input = AnalysisInput.model_validate(analysis_input_data)
    else:
        analysis_input = AnalysisInput(requirement=state["requirement"])

    report = PRISMReport(
        analysis_id=state["analysis_id"],
        requirement=state["requirement"],
        analysis_input=analysis_input,
    )

    # Build a path -> source_url lookup from the retrieved chunks so every
    # Citation can carry a clickable URL when the connector exposed one.
    # Chunks sharing a path also share a URL, so last-write-wins is fine.
    url_by_path: dict[str, str] = {}
    for chunk in chunks:
        path = chunk.metadata.source_path
        url = chunk.metadata.source_url
        if path and url:
            url_by_path[path] = url

    def _resolve_url(raw: str) -> str:
        """Match a citation label (which may be a raw path or an LLM label
        like ``Doc 1 - necrokings/RetryOps@main: README.md``) to a URL.

        Exact match first; otherwise substring-match against known paths so
        LLM-decorated labels still resolve.
        """
        if not raw:
            return ""
        if raw in url_by_path:
            return url_by_path[raw]
        for known, url in url_by_path.items():
            if known in raw:
                return url
        return ""

    def _cite(path: str) -> Citation:
        return Citation(document_path=path, source_url=_resolve_url(path))

    if synthesis:
        report.executive_summary = synthesis.executive_summary
        report.team_routing_narrative = synthesis.team_routing_narrative
        report.dependency_narrative = synthesis.dependency_narrative
        report.risk_narrative = synthesis.risk_narrative
        report.effort_narrative = synthesis.effort_narrative
        report.data_quality_summary = synthesis.data_quality_summary
        report.recommendations = synthesis.recommendations
        report.caveats = synthesis.caveats

    rd = _result_data(routing)
    if rd:
        primary = rd.get("primary_team", {})
        report.team_routing = TeamRouting(
            primary_team=TeamCandidate(
                name=primary.get("name", "Unknown"),
                confidence=primary.get("confidence", 0.0),
                justification=primary.get("justification", ""),
                sources=[_cite(s) for s in primary.get("key_sources", [])],
            ),
            supporting_teams=[
                TeamCandidate(
                    name=t.get("name", ""),
                    confidence=t.get("confidence", 0.0),
                    justification=t.get("justification", ""),
                    role=t.get("role", "supporting"),
                    sources=[_cite(s) for s in t.get("key_sources", [])],
                )
                for t in rd.get("supporting_teams", [])
            ],
        )

        report.affected_services = [
            AffectedService(
                name=s.get("name", ""),
                impact=s.get("impact", "informational"),
                owning_team=s.get("owning_team", ""),
                changes_needed=s.get("changes_needed", ""),
                sources=[_cite(d) for d in s.get("source_docs", [])],
            )
            for s in rd.get("affected_services", [])
        ]

    dd = _result_data(dependencies)
    if dd:
        report.dependencies = DependencyTree(
            blocking=[
                DependencyEdge(
                    from_service=d.get("from_service", ""),
                    to_service=d.get("to_service", ""),
                    dependency_type="blocking",
                    reason=d.get("reason", ""),
                    sources=[_cite(s) for s in d.get("source_docs", [])],
                )
                for d in dd.get("blocking", [])
            ],
            impacted=[
                DependencyEdge(
                    from_service=d.get("from_service", ""),
                    to_service=d.get("to_service", ""),
                    dependency_type="impacted",
                    reason=d.get("reason", ""),
                    sources=[_cite(s) for s in d.get("source_docs", [])],
                )
                for d in dd.get("impacted", [])
            ],
            informational=[
                DependencyEdge(
                    from_service=d.get("from_service", ""),
                    to_service=d.get("to_service", ""),
                    dependency_type="informational",
                    reason=d.get("reason", ""),
                    sources=[_cite(s) for s in d.get("source_docs", [])],
                )
                for d in dd.get("informational", [])
            ],
        )

    ra = _result_data(risk_assessment)
    if ra:
        report.risk_assessment = RiskAssessment(
            overall_risk=ra.get("overall_risk", "medium"),
            risks=[
                RiskItem(
                    category=r.get("category", "technical_complexity"),
                    level=r.get("level", "medium"),
                    description=r.get("description", ""),
                    mitigation=r.get("mitigation", ""),
                    sources=[_cite(s) for s in r.get("source_docs", [])],
                )
                for r in ra.get("risks", [])
            ],
        )
        report.effort_estimate = EffortEstimate(
            total_days_min=ra.get("total_days_min", 0),
            total_days_max=ra.get("total_days_max", 0),
            confidence=ra.get("effort_confidence", "low"),
            breakdown=[
                EffortBreakdown(
                    task=e.get("task", ""),
                    days_min=e.get("days_min", 0),
                    days_max=e.get("days_max", 0),
                    team=e.get("team", ""),
                )
                for e in ra.get("effort_breakdown", [])
            ],
            staffing=StaffingEstimate(
                engineers_needed=ra.get("staffing_engineers", 1),
                reviewers_needed=ra.get("staffing_reviewers", 1),
                estimated_calendar_weeks_min=ra.get("calendar_weeks_min", 1),
                estimated_calendar_weeks_max=ra.get("calendar_weeks_max", 4),
            ),
        )

    for c in conflicts:
        owners = c.get("owners", [])
        claimants = [
            ConflictClaimant(
                team=str(o.get("team", "")),
                confidence=o.get("confidence", "inferred")
                if o.get("confidence") in ("explicit", "inferred")
                else "inferred",
                source=str(o.get("source", "")),
                updated=str(o.get("updated", "")),
            )
            for o in owners
            if isinstance(o, dict)
        ]
        team_names = [cl.team for cl in claimants]
        unique_lower = set(t.lower().replace("-", " ").replace("_", " ") for t in team_names)
        if len(unique_lower) == 1 and len(team_names) > 1:
            resolution = f"Likely the same team referenced under different names ({', '.join(team_names)}). Consider standardizing naming."
        elif len(team_names) > 1:
            resolution = f"Multiple teams claim ownership: {', '.join(team_names)}. Recommend clarifying ownership with team leads."
        else:
            resolution = ""
        report.conflicts_detected.append(
            OwnershipConflict(
                service=c.get("service", ""),
                claimed_by=claimants,
                resolution=resolution,
            )
        )

    if stale_sources:
        report.staleness_warnings = [
            f"{len(stale_sources)} source(s) last updated over "
            f"{settings.staleness_threshold_days} days ago. Consider verifying accuracy."
        ] + stale_sources[:5]

    cd = _result_data(coverage)
    if cd:
        report.coverage_report = CoverageReport(
            documents_retrieved=cd.get("documents_retrieved", 0),
            documents_cited=cd.get("documents_cited", 0),
            platforms_searched=cd.get("platforms_searched", []),
            gaps=cd.get("gaps", []),
            critical_gaps=cd.get("critical_gaps", []),
            stale_sources=cd.get("stale_sources", []),
            retrieval_rounds=state.get("retrieval_rounds", 0),
        )
        if not report.coverage_report.stale_sources and stale_sources:
            report.coverage_report.stale_sources = stale_sources[:10]

    claims_by_doc: dict[str, list[str]] = {}
    citation_data = _result_data(citation_result)
    if citation_data:
        verified_claims = [
            VerifiedClaim(
                claim=c.get("claim", ""),
                supporting_doc=c.get("supporting_doc", ""),
                excerpt=c.get("excerpt", ""),
                confidence=c.get("confidence", "medium"),
            )
            for c in citation_data.get("verified_claims", [])
        ]
        report.verification_report = VerificationReport(
            verified_claims=verified_claims,
            unsupported_claims=citation_data.get("unsupported_claims", []),
            stale_source_warnings=citation_data.get("stale_source_warnings", []),
        )

        cited_docs = {claim.supporting_doc for claim in verified_claims if claim.supporting_doc}
        if cited_docs and report.coverage_report.documents_cited == 0:
            report.coverage_report.documents_cited = len(cited_docs)

        for claim in verified_claims:
            if claim.supporting_doc and claim.claim:
                claims_by_doc.setdefault(claim.supporting_doc, []).append(claim.claim)

    if not report.data_quality_summary:
        data_quality_notes = []
        if report.coverage_report.critical_gaps:
            data_quality_notes.append(
                f"{len(report.coverage_report.critical_gaps)} critical gap(s) need manual validation"
            )
        if report.verification_report.unsupported_claims:
            data_quality_notes.append(
                f"{len(report.verification_report.unsupported_claims)} unsupported claim(s) remain"
            )
        if report.staleness_warnings:
            data_quality_notes.append("Some supporting documents are stale")
        if data_quality_notes:
            report.data_quality_summary = ". ".join(data_quality_notes) + "."

    if not report.executive_summary:
        summary_bits = []
        if report.team_routing:
            summary_bits.append(f"Likely primary owner: {report.team_routing.primary_team.name}.")
        if report.affected_services:
            services = ", ".join(service.name for service in report.affected_services[:4])
            summary_bits.append(f"Affected services include {services}.")
        if report.risk_assessment:
            summary_bits.append(f"Overall risk is {report.risk_assessment.overall_risk}.")
        if report.effort_estimate:
            summary_bits.append(
                f"Estimated effort is {report.effort_estimate.total_days_min}-{report.effort_estimate.total_days_max} person-days."
            )
        report.executive_summary = " ".join(summary_bits)

    report.impact_matrix = _build_impact_matrix(report)

    seen_paths = set()
    for chunk in chunks:
        path = chunk.metadata.source_path
        if path in seen_paths:
            continue
        seen_paths.add(path)
        modified = chunk.metadata.last_modified.strftime("%Y-%m-%d") if chunk.metadata.last_modified else ""
        report.all_sources.append(
            SourceDocument(
                id=chunk.document_id,
                path=path,
                platform=chunk.metadata.source_platform,
                source_url=chunk.metadata.source_url or url_by_path.get(path, ""),
                relevance_score=chunk.score,
                last_modified=modified,
                is_stale=any(path in s for s in stale_sources),
                sections_cited=claims_by_doc.get(path, [])[:5],
            )
        )

    return report


def _build_impact_matrix(report: PRISMReport) -> list[ImpactMatrixRow]:
    rows: list[ImpactMatrixRow] = []
    seen: set[tuple[str, str, str]] = set()

    primary_team = report.team_routing.primary_team if report.team_routing else None
    supporting_teams = report.team_routing.supporting_teams if report.team_routing else []
    confidence_by_team = {
        team.name: _confidence_label(team.confidence)
        for team in ([primary_team] if primary_team else []) + supporting_teams
    }

    blockers_by_service: dict[str, list[str]] = {}
    evidence_by_service: dict[str, list[str]] = {}

    for edge in report.dependencies.blocking:
        blocker_text = edge.reason or f"Blocked by dependency on {edge.to_service}"
        for service_name in {edge.from_service, edge.to_service}:
            if not service_name:
                continue
            blockers_by_service.setdefault(service_name, []).append(blocker_text)
            evidence_by_service.setdefault(service_name, []).extend(
                citation.document_path for citation in edge.sources if citation.document_path
            )

    for conflict in report.conflicts_detected:
        blocker_text = conflict.resolution or "Ownership requires clarification."
        blockers_by_service.setdefault(conflict.service, []).append(blocker_text)
        for claimant in conflict.claimed_by:
            evidence_by_service.setdefault(conflict.service, []).append(claimant.source)

    def add_row(
        *,
        team: str,
        service: str,
        role: str,
        why_involved: str,
        confidence: str,
        blocker: str = "",
        evidence: list[str] | None = None,
    ) -> None:
        normalized_team = team.strip()
        normalized_service = service.strip()
        if not normalized_team or not normalized_service:
            return

        key = (normalized_team.lower(), normalized_service.lower(), role.lower())
        if key in seen:
            return

        seen.add(key)
        rows.append(
            ImpactMatrixRow(
                team=normalized_team,
                service=normalized_service,
                role=role,
                why_involved=why_involved.strip(),
                confidence=confidence if confidence in {"high", "medium", "low"} else "medium",
                blocker=blocker.strip(),
                evidence=_dedupe_strings((evidence or []) + evidence_by_service.get(normalized_service, []))[:5],
            )
        )

    for service in report.affected_services:
        owner_team = service.owning_team.strip()
        service_blockers = blockers_by_service.get(service.name, [])
        blocker = service_blockers[0] if service_blockers else ""
        base_evidence = [citation.document_path for citation in service.sources if citation.document_path]
        why_involved = service.changes_needed or f"Service marked as {service.impact} impact."

        if owner_team:
            add_row(
                team=owner_team,
                service=service.name,
                role="owner",
                why_involved=why_involved,
                confidence=confidence_by_team.get(owner_team, "medium"),
                blocker=blocker,
                evidence=base_evidence,
            )
        elif primary_team:
            add_row(
                team=primary_team.name,
                service=service.name,
                role="primary",
                why_involved=why_involved or primary_team.justification,
                confidence=_confidence_label(primary_team.confidence),
                blocker=blocker,
                evidence=base_evidence
                + [citation.document_path for citation in primary_team.sources if citation.document_path],
            )

        for team in supporting_teams:
            if owner_team and team.name == owner_team:
                continue
            add_row(
                team=team.name,
                service=service.name,
                role=team.role or "supporting",
                why_involved=team.justification or why_involved,
                confidence=_confidence_label(team.confidence),
                blocker=blocker,
                evidence=base_evidence
                + [citation.document_path for citation in team.sources if citation.document_path],
            )

    for conflict in report.conflicts_detected:
        for claimant in conflict.claimed_by:
            add_row(
                team=claimant.team,
                service=conflict.service,
                role="conflict",
                why_involved="Claims ownership of the service.",
                confidence="medium" if claimant.confidence == "explicit" else "low",
                blocker=conflict.resolution or "Ownership needs clarification.",
                evidence=[claimant.source],
            )

    rows.sort(
        key=lambda row: (
            {"owner": 0, "primary": 1, "supporting": 2, "conflict": 3}.get(row.role, 4),
            row.team.lower(),
            row.service.lower(),
        )
    )
    return rows


def _confidence_label(score: float) -> str:
    normalized = score / 100 if score > 1 else score
    if normalized >= 0.75:
        return "high"
    if normalized >= 0.45:
        return "medium"
    return "low"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def create_workflow() -> StateGraph:
    workflow = StateGraph(OrchestratorState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("route", route_node)
    workflow.add_node("dependencies", deps_node)
    workflow.add_node("risk_effort", risk_node)
    workflow.add_node("coverage", coverage_node)
    workflow.add_node("citations", citation_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("chat", chat_node)

    workflow.set_entry_point("plan")
    # Plan branches: chat-mode follow-ups answer from prior context and exit;
    # full-mode runs the normal pipeline.
    workflow.add_conditional_edges(
        "plan",
        route_after_plan,
        {"chat": "chat", "retrieve": "retrieve"},
    )
    workflow.add_edge("chat", END)

    workflow.add_edge("retrieve", "route")
    workflow.add_edge("route", "dependencies")
    workflow.add_edge("dependencies", "risk_effort")
    workflow.add_edge("risk_effort", "coverage")

    workflow.add_conditional_edges(
        "coverage",
        should_retrieve_more,
        {"retrieve": "retrieve", "citations": "citations"},
    )

    workflow.add_edge("citations", "synthesize")
    workflow.add_edge("synthesize", END)

    return workflow


async def create_compiled_app(checkpointer=None):
    global _compiled_app, _compiled_app_has_checkpointer, _checkpointer_stack

    if checkpointer is not None:
        workflow = create_workflow()
        return workflow.compile(checkpointer=checkpointer)

    if _compiled_app is not None and _compiled_app_has_checkpointer:
        return _compiled_app

    async with _get_compiled_app_lock():
        if _compiled_app is not None and _compiled_app_has_checkpointer:
            return _compiled_app

        workflow = create_workflow()
        resolved_checkpointer = None

        try:
            stack = AsyncExitStack()
            saver = await stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(settings.postgres_url)
            )
            await saver.setup()
            resolved_checkpointer = saver
            _checkpointer_stack = stack
            log.info("analysis_checkpointer_initialized")
        except Exception as e:
            log.warning("checkpointer_setup_failed", error=str(e))
            if "stack" in locals():
                await stack.aclose()

        if resolved_checkpointer is not None:
            _compiled_app = workflow.compile(checkpointer=resolved_checkpointer)
            _compiled_app_has_checkpointer = True
        elif _compiled_app is None:
            _compiled_app = workflow.compile(checkpointer=None)
            _compiled_app_has_checkpointer = False

        return _compiled_app


async def shutdown_compiled_app() -> None:
    global _compiled_app, _compiled_app_has_checkpointer, _checkpointer_stack

    async with _get_compiled_app_lock():
        _compiled_app = None
        _compiled_app_has_checkpointer = False
        if _checkpointer_stack is not None:
            await _checkpointer_stack.aclose()
            _checkpointer_stack = None
            log.info("analysis_checkpointer_closed")


@dataclass
class AnalysisResult:
    """Result of a single analysis run.

    For ``kind == "full"``, ``report`` is the full PRISMReport.
    For ``kind == "chat"``, ``report`` is a minimal shell (exec_summary =
    chat answer) and ``chat_answer`` holds the raw payload.
    """

    analysis_id: str
    kind: str
    report: PRISMReport
    chat_answer: dict | None
    rolling_summary: str
    plan: dict | None


async def _summarize_turn(
    analysis_id: str,
    requirement: str,
    kind: str,
    body: str,
) -> str:
    """Run the rolling summarizer. Best-effort -- if the LLM fails we just
    store an empty summary and future turns fall back to the exec summary."""
    try:
        result = await llm_call(
            prompt=build_rolling_summary_prompt(
                requirement=requirement,
                kind=kind,
                report_or_answer=body,
            ),
            system_prompt=ROLLING_SUMMARY_SYSTEM_PROMPT,
            output_schema=RollingSummaryOutput,
            model=settings.model_router,
            agent_name="summarize",
            analysis_id=analysis_id,
        )
        return result.summary
    except Exception as e:  # noqa: BLE001
        log.warning("rolling_summary_failed", analysis_id=analysis_id, error=str(e))
        return ""


async def run_analysis(
    requirement: str,
    analysis_id: str | None = None,
    analysis_input: AnalysisInput | dict | None = None,
    on_step: Any = None,
    prior_turns: list[dict] | None = None,
) -> AnalysisResult:
    analysis_id = analysis_id or str(uuid.uuid4())
    prior_turns = prior_turns or []
    log.info(
        "analysis_start",
        analysis_id=analysis_id,
        requirement=requirement[:100],
        prior_turn_count=len(prior_turns),
    )
    start_time = time.time()

    if analysis_input is None:
        normalized_input = AnalysisInput(requirement=requirement)
    elif isinstance(analysis_input, AnalysisInput):
        normalized_input = analysis_input
    else:
        normalized_input = AnalysisInput.model_validate(analysis_input)

    analysis_brief = build_analysis_brief(normalized_input)
    search_query = build_search_query(normalized_input)

    app = await create_compiled_app()

    if on_step is not None:
        register_step_callback(analysis_id, on_step)

    initial_state = {
        "requirement": requirement,
        "analysis_id": analysis_id,
        "analysis_input": normalized_input.model_dump(),
        "analysis_brief": analysis_brief,
        "search_query": search_query,
        "retrieved_chunks": [],
        "plan": None,
        "prior_turns": prior_turns,
        "team_routing": None,
        "dependencies": None,
        "risk_assessment": None,
        "coverage_report": None,
        "citation_result": None,
        "stale_sources": [],
        "conflicts": [],
        "retrieval_rounds": 0,
        "agent_trace": [],
        "final_report": None,
        "chat_answer": None,
    }

    config = {"configurable": {"thread_id": f"analysis-{analysis_id}"}}

    try:
        final_state = await app.ainvoke(initial_state, config=config)
    finally:
        clear_step_callback(analysis_id)

    duration = time.time() - start_time

    plan = final_state.get("plan") or {}
    mode = plan.get("mode", "full") if isinstance(plan, dict) else "full"
    chat_answer = final_state.get("chat_answer")

    if mode == "chat" and chat_answer:
        # Chat-mode: minimal report shell; the real payload is chat_answer.
        answer_text = chat_answer.get("answer", "")
        report = PRISMReport(
            analysis_id=analysis_id,
            requirement=requirement,
            executive_summary=answer_text,
            duration_seconds=duration,
        )
        rolling_summary = await _summarize_turn(
            analysis_id=analysis_id,
            requirement=requirement,
            kind="chat",
            body=answer_text,
        )
        kind = "chat"
    else:
        report_data = final_state.get("final_report", {})
        if report_data:
            report = PRISMReport.model_validate(report_data)
            report.duration_seconds = duration
        else:
            report = PRISMReport(
                analysis_id=analysis_id,
                requirement=requirement,
                duration_seconds=duration,
            )
        rolling_summary = await _summarize_turn(
            analysis_id=analysis_id,
            requirement=requirement,
            kind="full",
            body=report.executive_summary or requirement,
        )
        kind = "full"

    log.info(
        "analysis_complete",
        analysis_id=analysis_id,
        kind=kind,
        duration=f"{duration:.1f}s",
    )
    return AnalysisResult(
        analysis_id=analysis_id,
        kind=kind,
        report=report,
        chat_answer=chat_answer if kind == "chat" else None,
        rolling_summary=rolling_summary,
        plan=plan if isinstance(plan, dict) else None,
    )
