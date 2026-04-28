from __future__ import annotations

from sentence_transformers import CrossEncoder

from src.config import settings
from src.models.chunk import Chunk
from src.observability.logging import get_logger

log = get_logger("reranker")

_model: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    global _model
    if _model is None:
        log.info("loading_reranker", model=settings.reranker_model)
        _model = CrossEncoder(settings.reranker_model)
        log.info("reranker_loaded")
    return _model


DOC_TYPE_AGENT_RELEVANCE = {
    "router": {"wiki", "readme", "spreadsheet", "service_catalog", "architecture_doc"},
    "dependency": {"wiki", "readme", "runbook", "issue", "architecture_doc"},
    "risk": {"issue", "runbook", "meeting_notes", "incident_report"},
    "effort": {"issue", "merge_request", "meeting_notes", "spreadsheet"},
    "coverage": {"wiki", "readme", "spreadsheet", "service_catalog", "runbook", "architecture_doc"},
}


def rerank_for_agent(
    chunks: list[Chunk],
    requirement: str,
    agent_type: str,
    top_k: int | None = None,
) -> list[Chunk]:
    top_k = top_k or settings.rerank_top_k
    if not chunks:
        return []

    relevant_types = DOC_TYPE_AGENT_RELEVANCE.get(agent_type)
    if relevant_types:
        type_filtered = [c for c in chunks if c.metadata.doc_type in relevant_types]
        candidates = type_filtered if len(type_filtered) >= 3 else chunks
    else:
        candidates = chunks

    return _rerank(candidates, requirement, top_k, label=f"agent:{agent_type}")


def rerank_chunks(
    chunks: list[Chunk],
    requirement: str,
    top_k: int | None = None,
) -> list[Chunk]:
    """Doc-type-agnostic rerank for the chat surface.

    The agent reranker filters by ``DOC_TYPE_AGENT_RELEVANCE`` first --
    that's right for analysis pipelines that know what kind of evidence
    each agent needs (a risk agent shouldn't see catalog docs). Chat
    has no such prior; a question can land on any doc type. Skip the
    type filter and let the cross-encoder rank purely on relevance.
    """
    top_k = top_k or settings.rerank_top_k
    if not chunks:
        return []
    return _rerank(chunks, requirement, top_k, label="chat")


def _rerank(
    candidates: list[Chunk],
    requirement: str,
    top_k: int,
    *,
    label: str,
) -> list[Chunk]:
    reranker = get_reranker()
    pairs = [(requirement, c.content) for c in candidates]
    scores = reranker.predict(pairs)

    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

    result = []
    for chunk, score in scored[:top_k]:
        chunk.score = float(score)
        result.append(chunk)

    log.info("reranked", label=label, input=len(candidates), output=len(result))
    return result
