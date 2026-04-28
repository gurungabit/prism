"""Agentic refinement: one bounded re-search when the first pass is weak.

After the primary retrieval (expansion + HyDE + hybrid + rerank) the
chat surface peeks at the result quality. If it's thin -- fewer than
``chat_refine_min_chunks`` results, or the top score is below
``chat_refine_max_score`` -- the LLM is asked to reformulate the query
into a search-friendlier form and we run one more retrieval pass.
Results are merged (refined first, then originals fill the rest) so
the user gets a strict superset of the first pass.

This is intentionally NOT a full agentic-RAG tool loop. Tool loops
work but they're expensive (extra LLM round trips per turn) and they
can spiral on degenerate queries. A single bounded retry catches the
common "the user phrased it differently than the docs" case at modest
cost.
"""

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
) -> list[Chunk]:
    """If ``chunks`` looks thin, run one refined retrieval pass and
    merge. Returns the (possibly augmented) chunk list.

    ``engine`` is a ``HybridSearchEngine`` -- typed as ``Any`` here to
    avoid a circular import with the chat module.
    """
    if not settings.chat_agentic_refine:
        return chunks

    if not _looks_weak(chunks):
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
            top_k=settings.chat_retrieval_top_k,
            expand=settings.chat_query_expansion,
            scope_filter=scope_filter,
            use_hyde=settings.chat_use_hyde,
        )
    except Exception as e:  # noqa: BLE001
        # Don't let a refine failure poison the original results --
        # caller already has something usable.
        log.warning("agentic_refine_search_failed", error=str(e)[:200])
        return chunks

    merged = _merge_unique(refined_chunks, chunks)
    if settings.chat_rerank and merged:
        # Same defensive shape as the chat-side rerank: a cross-encoder
        # failure on the merged set must not poison results we already
        # had from the primary pass. Fall back to the merged-but-not-
        # reranked list, capped to the same top-k.
        try:
            merged = rerank_chunks(
                merged,
                requirement=original_query,
                top_k=settings.chat_rerank_top_k,
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


def _looks_weak(chunks: list[Chunk]) -> bool:
    if len(chunks) < settings.chat_refine_min_chunks:
        return True
    if _top_score(chunks) < settings.chat_refine_max_score:
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
        # Strip stray quotes or trailing punctuation the model sometimes
        # adds despite the prompt.
        text = text.strip("\"' \n\t")
        return text or None
    except Exception as e:  # noqa: BLE001
        log.warning("query_rewrite_failed", error=str(e)[:200])
        return None
