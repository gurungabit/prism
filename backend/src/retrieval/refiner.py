"""One bounded LLM-rewrite + re-search when the first chat pass is weak."""

from __future__ import annotations

from src.config import settings
from src.llm_client import get_llm_client
from src.models.chunk import Chunk
from src.observability.logging import get_logger
from src.retrieval.reranker import rerank_chunks

log = get_logger("refiner")

_REFINE_SYSTEM = (
    "You rewrite a user's chat question into a search query optimized "
    "for retrieving internal organization documentation. The first "
    "retrieval pass came back thin, so the user's phrasing probably "
    "didn't line up with the docs.\n\n"
    "RULES:\n"
    "- Output ONE rewritten query, no preamble, no JSON, no quotes.\n"
    "- Keep proper nouns verbatim.\n"
    "- Replace verbs with documentation-style nouns where natural "
    "('what does X call' -> 'X external integrations').\n"
    "- Drop conversational filler ('can you tell me', 'I want to "
    "know').\n"
    "- Stay under 15 words."
)


async def maybe_refine_retrieval(
    engine,
    *,
    chunks: list[Chunk],
    original_query: str,
    scope_filter: dict | None,
    enabled: bool | None = None,
    min_chunks: int | None = None,
    max_score: float | None = None,
    retrieval_top_k: int | None = None,
    query_expansion: bool | None = None,
    use_hyde: bool | None = None,
    rerank_enabled: bool | None = None,
    rerank_top_k: int | None = None,
) -> list[Chunk]:
    """Return ``chunks`` augmented with a refined pass if the first looks thin."""
    if enabled is None:
        enabled = settings.chat_agentic_refine
    if not enabled:
        return chunks

    if min_chunks is None:
        min_chunks = settings.chat_refine_min_chunks
    if max_score is None:
        max_score = settings.chat_refine_max_score
    if retrieval_top_k is None:
        retrieval_top_k = settings.chat_retrieval_top_k
    if query_expansion is None:
        query_expansion = settings.chat_query_expansion
    if use_hyde is None:
        use_hyde = settings.chat_use_hyde
    if rerank_enabled is None:
        rerank_enabled = settings.chat_rerank
    if rerank_top_k is None:
        rerank_top_k = settings.chat_rerank_top_k

    if not _looks_weak(chunks, min_chunks=min_chunks, max_score=max_score):
        return chunks

    refined_query = await _rewrite_query(original_query)
    if not refined_query or refined_query.strip() == original_query.strip():
        return chunks

    log.info(
        "agentic_refine_triggered",
        original_chars=len(original_query),
        refined=refined_query[:120],
        first_pass_count=len(chunks),
        first_pass_top_score=_top_score(chunks),
    )

    try:
        refined_chunks = await engine.search(
            requirement=refined_query,
            top_k=retrieval_top_k,
            expand=query_expansion,
            scope_filter=scope_filter,
            use_hyde=use_hyde,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("agentic_refine_search_failed", error=str(e)[:200])
        return chunks

    merged = _merge_unique(refined_chunks, chunks)
    if rerank_enabled and merged:
        try:
            merged = rerank_chunks(
                merged,
                requirement=original_query,
                top_k=rerank_top_k,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "refiner_rerank_failed_using_merged",
                error=str(e)[:200],
            )
            merged = merged[: settings.chat_rerank_top_k]

    log.info(
        "agentic_refine_complete",
        merged_count=len(merged),
        added=max(0, len(merged) - len(chunks)),
    )
    return merged


def _looks_weak(chunks: list[Chunk], *, min_chunks: int, max_score: float) -> bool:
    if len(chunks) < min_chunks:
        return True
    if _top_score(chunks) < max_score:
        return True
    return False


def _top_score(chunks: list[Chunk]) -> float:
    return max((c.score for c in chunks), default=0.0)


def _merge_unique(primary: list[Chunk], secondary: list[Chunk]) -> list[Chunk]:
    seen = set()
    merged: list[Chunk] = []
    for chunk in [*primary, *secondary]:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged.append(chunk)
    return merged


async def _rewrite_query(query: str) -> str | None:
    try:
        client = get_llm_client()
        response = await client.chat.completions.create(
            model=settings.model_bulk,
            messages=[
                {"role": "system", "content": _REFINE_SYSTEM},
                {"role": "user", "content": query},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        text = text.strip("\"' \n\t")
        return text or None
    except Exception as e:  # noqa: BLE001
        log.warning("query_rewrite_failed", error=str(e)[:200])
        return None
