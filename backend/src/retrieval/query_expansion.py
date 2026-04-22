from __future__ import annotations

import json
from collections import OrderedDict

from pydantic import BaseModel

from src.config import settings
from src.llm_client import get_llm_client
from src.observability.logging import get_logger

log = get_logger("query_expansion")

_query_cache: OrderedDict[str, list[str]] = OrderedDict()
_MAX_CACHE_ENTRIES = 128


class ExpandedQueries(BaseModel):
    variants: list[str]


EXPANSION_SYSTEM_PROMPT = (
    "You generate search query variants for a hybrid search system. "
    "Given a requirement, produce 5 diverse search queries that would find relevant documentation. "
    "Include: synonyms, acronyms, related technical terms, and different phrasings. "
    "Each query should target a different angle of the requirement."
)


async def expand_queries(requirement: str) -> list[str]:
    cached = _query_cache.get(requirement)
    if cached is not None:
        _query_cache.move_to_end(requirement)
        log.info("queries_expanded_from_cache", count=len(cached))
        return list(cached)

    try:
        schema_hint = json.dumps(ExpandedQueries.model_json_schema(), separators=(",", ":"))
        structured_system = (
            f"{EXPANSION_SYSTEM_PROMPT}\n\n"
            f"Respond with a single JSON object matching this schema:\n{schema_hint}\n"
            "Return ONLY the JSON object — no prose, no code fences."
        )

        client = get_llm_client()
        response = await client.chat.completions.create(
            model=settings.model_bulk,
            messages=[
                {"role": "system", "content": structured_system},
                {"role": "user", "content": f"Generate 5 search query variants for this requirement:\n\n{requirement}"},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""
        parsed = json.loads(content)
        result = ExpandedQueries.model_validate(parsed)
        _remember_queries(requirement, result.variants)
        log.info("queries_expanded", count=len(result.variants))
        return result.variants

    except Exception as e:
        log.warning("query_expansion_failed_using_fallback", error=str(e)[:100])
        fallback = _fallback_expand(requirement)
        _remember_queries(requirement, fallback)
        return fallback


def _remember_queries(requirement: str, variants: list[str]) -> None:
    _query_cache[requirement] = list(variants)
    _query_cache.move_to_end(requirement)
    while len(_query_cache) > _MAX_CACHE_ENTRIES:
        _query_cache.popitem(last=False)


def _fallback_expand(requirement: str) -> list[str]:
    variants = [requirement]

    words = requirement.lower().split()
    if len(words) > 3:
        variants.append(" ".join(words[: len(words) // 2]))
        variants.append(" ".join(words[len(words) // 2 :]))

    return variants
