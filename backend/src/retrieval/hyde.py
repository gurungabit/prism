"""HyDE: ask the LLM for a hypothetical answer to use as the vector probe."""

from __future__ import annotations

from collections import OrderedDict

from src.config import settings
from src.llm_client import get_llm_client
from src.observability.logging import get_logger

log = get_logger("hyde")

_HYDE_SYSTEM = (
    "You write short hypothetical answers used as a retrieval probe in "
    "a vector search system. Given a question about an organization's "
    "services, teams, dependencies, or documentation, draft a 2-4 "
    "sentence answer in the voice of an internal README or wiki page. "
    "Use plausible technical vocabulary even if you don't know the "
    "specific answer -- the goal is a passage that LOOKS like the "
    "documentation we want to find, not a real answer. Do NOT add "
    "qualifiers ('I don't know', 'it depends'); just write the "
    "hypothetical."
)

_cache: OrderedDict[str, str] = OrderedDict()
_MAX_CACHE = 128


async def hypothetical_answer(query: str) -> str | None:
    """Return a short hypothetical answer, or ``None`` on LLM failure."""
    cached = _cache.get(query)
    if cached is not None:
        _cache.move_to_end(query)
        return cached

    try:
        client = get_llm_client()
        response = await client.chat.completions.create(
            model=settings.model_bulk,
            messages=[
                {"role": "system", "content": _HYDE_SYSTEM},
                {"role": "user", "content": query},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return None
        if len(text) > settings.hyde_max_chars:
            text = text[: settings.hyde_max_chars]
        _remember(query, text)
        log.info("hyde_generated", chars=len(text))
        return text
    except Exception as e:  # noqa: BLE001
        log.warning("hyde_generation_failed", error=str(e)[:200])
        return None


def _remember(query: str, text: str) -> None:
    _cache[query] = text
    _cache.move_to_end(query)
    while len(_cache) > _MAX_CACHE:
        _cache.popitem(last=False)
