from __future__ import annotations

import json
import re
from typing import Any

from src.agents.llm import llm_call
from src.agents.prompts import CITATION_SYSTEM_PROMPT, build_citation_prompt
from src.agents.result import AgentResult
from src.agents.schemas import CitationVerification, VerifiedClaim
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
        verification = _normalize_verification_sources(verification, chunks)
        if not verification.verified_claims:
            verification = _add_structured_fallback_claims(
                verification,
                routing,
                dependencies,
                risk_assessment,
                chunks,
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
        fallback = _fallback_verification_from_agent_outputs(
            routing,
            dependencies,
            risk_assessment,
            chunks,
        )
        if on_step:
            if fallback.verified_claims:
                await on_step(
                    {
                        "agent": "citation",
                        "action": "results",
                        "detail": (
                            f"Fallback: {len(fallback.verified_claims)} "
                            "structured citations"
                        ),
                        "data": {
                            "verified_claims": [
                                f"{c.claim[:80]}... ({c.confidence})"
                                for c in fallback.verified_claims[:6]
                            ],
                            "unsupported_claims": [],
                            "stale_warnings": [],
                        },
                    }
                )
            await on_step({"agent": "citation", "action": "failed", "detail": str(e)[:200]})
        return {
            "citation_result": AgentResult(
                status="partial",
                data=fallback.model_dump(),
                error=str(e),
                degradation_note=(
                    "Citation LLM validation failed; used structured agent "
                    "source references as fallback verification."
                ),
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
    if not chunks:
        return "No source documents available"

    from src.agents.prompts import format_chunks_for_prompt

    return format_chunks_for_prompt(chunks, max_chars_per_chunk=900)


def _normalize_verification_sources(
    verification: CitationVerification,
    chunks: list[Chunk],
) -> CitationVerification:
    """Keep verified claims only when the cited label maps to a retrieved path.

    Citation validation is only useful if its supporting_doc is linkable. The
    model may return "Doc 3" or a decorated label; normalize substring matches
    back to the raw source path and move unresolvable claims to unsupported.
    """
    known_paths = sorted(
        {chunk.metadata.source_path for chunk in chunks if chunk.metadata.source_path},
        key=len,
        reverse=True,
    )
    source_label_paths = {
        str(index): chunk.metadata.source_path
        for index, chunk in enumerate(chunks, 1)
        if chunk.metadata.source_path
    }
    unsupported = list(verification.unsupported_claims)
    verified = []

    for claim in verification.verified_claims:
        resolved = _resolve_source_path(
            claim.supporting_doc,
            known_paths,
            source_label_paths,
        )
        if not resolved:
            unsupported.append(claim.claim)
            continue
        claim.supporting_doc = resolved
        verified.append(claim)

    verification.verified_claims = verified
    verification.unsupported_claims = _dedupe_strings(unsupported)
    return verification


def _add_structured_fallback_claims(
    verification: CitationVerification,
    routing,
    dependencies,
    risk_assessment,
    chunks: list[Chunk],
) -> CitationVerification:
    """Preserve structured source references when validator output is empty.

    A valid-but-overcautious citation response should not erase source-backed
    claims already emitted by the routing/dependency/risk agents.
    """
    fallback = _fallback_verification_from_agent_outputs(
        routing,
        dependencies,
        risk_assessment,
        chunks,
    )
    if not fallback.verified_claims:
        return verification
    verification.verified_claims = fallback.verified_claims
    if not verification.unsupported_claims:
        verification.unsupported_claims = fallback.unsupported_claims
    return verification


def _fallback_verification_from_agent_outputs(
    routing,
    dependencies,
    risk_assessment,
    chunks: list[Chunk],
) -> CitationVerification:
    known_paths = sorted(
        {chunk.metadata.source_path for chunk in chunks if chunk.metadata.source_path},
        key=len,
        reverse=True,
    )
    source_label_paths = {
        str(index): chunk.metadata.source_path
        for index, chunk in enumerate(chunks, 1)
        if chunk.metadata.source_path
    }
    excerpt_by_path = _excerpt_by_path(chunks)
    verified: list[VerifiedClaim] = []

    def add_claim(claim: str, source_docs: list[Any]) -> None:
        text = _short_claim(claim)
        if not text:
            return
        for raw_doc in source_docs[:3]:
            path = _resolve_source_path(str(raw_doc), known_paths, source_label_paths)
            if not path:
                continue
            verified.append(
                VerifiedClaim(
                    claim=text,
                    supporting_doc=path,
                    excerpt=excerpt_by_path.get(path, ""),
                    confidence="medium",
                )
            )

    rdata = routing.data if routing and isinstance(routing.data, dict) else {}
    primary = rdata.get("primary_team", {}) if isinstance(rdata, dict) else {}
    if isinstance(primary, dict):
        add_claim(
            f"Primary owner: {primary.get('name', '')}. {primary.get('justification', '')}",
            primary.get("key_sources", []) or [],
        )
    for service in rdata.get("affected_services", []) or []:
        if isinstance(service, dict):
            add_claim(
                f"{service.get('name', '')}: {service.get('changes_needed', '')}",
                service.get("source_docs", []) or [],
            )

    ddata = dependencies.data if dependencies and isinstance(dependencies.data, dict) else {}
    if isinstance(ddata, dict):
        for key in ("upstream_teams", "downstream_teams", "blocking", "impacted", "informational"):
            for item in ddata.get(key, []) or []:
                if isinstance(item, dict):
                    add_claim(item.get("reason", ""), item.get("source_docs", []) or [])

    risk_data = (
        risk_assessment.data
        if risk_assessment and isinstance(risk_assessment.data, dict)
        else {}
    )
    if isinstance(risk_data, dict):
        for risk in risk_data.get("risks", []) or []:
            if isinstance(risk, dict):
                add_claim(risk.get("description", ""), risk.get("source_docs", []) or [])

    deduped: dict[tuple[str, str], VerifiedClaim] = {}
    for claim in verified:
        deduped.setdefault((claim.claim.lower(), claim.supporting_doc), claim)

    return CitationVerification(verified_claims=list(deduped.values())[:80])


def _excerpt_by_path(chunks: list[Chunk]) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        path = chunk.metadata.source_path
        if path and path not in out:
            out[path] = " ".join(chunk.content.split())[:500]
    return out


def _short_claim(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    return text[:500]


def _resolve_source_path(
    raw: str,
    known_paths: list[str],
    source_label_paths: dict[str, str] | None = None,
) -> str:
    if not raw:
        return ""
    if raw in known_paths:
        return raw
    if source_label_paths:
        match = re.search(r"\b(?:source|doc(?:ument)?)\s*#?\s*(\d+)\b", raw, re.IGNORECASE)
        if match:
            return source_label_paths.get(match.group(1), "")
    for path in known_paths:
        if path in raw:
            return path
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = value.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out
