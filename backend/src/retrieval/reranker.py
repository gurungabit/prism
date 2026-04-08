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

    reranker = get_reranker()
    pairs = [(requirement, c.content) for c in candidates]
    scores = reranker.predict(pairs)

    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

    result = []
    for chunk, score in scored[:top_k]:
        chunk.score = float(score)
        result.append(chunk)

    log.info("reranked", agent=agent_type, input=len(candidates), output=len(result))
    return result
