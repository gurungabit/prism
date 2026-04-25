from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import AsyncGenerator

from src.config import settings
from src.llm_client import get_llm_client
from src.observability.logging import get_logger
from src.retrieval.hybrid_search import HybridSearchEngine, RetrievalUnavailable

log = get_logger("chat")

_conversations: dict[str, list[dict]] = defaultdict(list)


async def chat_stream(
    message: str,
    conversation_id: str | None = None,
    *,
    scope: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream a grounded chat answer.

    ``scope`` is a ``{org_id, team_ids, service_ids}`` dict pushed down into
    OpenSearch so the retrieved chunks stay inside the user's selected
    catalog scope. ``None`` means un-scoped retrieval (legacy path).
    """
    conversation_id = conversation_id or str(uuid.uuid4())

    # Stage the user message locally rather than appending immediately.
    # The previous flow appended at the start of the turn and counted on
    # the LLM-success branch to pair it with an assistant message. When
    # retrieval / LLM failed, the user-only message stayed in
    # ``_conversations`` and bled into the next request's
    # ``history_text`` + the conversation preview -- a failed
    # infrastructure attempt would shape future chat context. Now we
    # only commit the pair *after* the assistant response finishes,
    # which makes the failed-turn comments below actually true.
    pending_user_message = {"role": "user", "content": message}

    # Only treat scope as active when ``org_id`` is present -- the wider
    # ``HybridSearchEngine`` contract requires it as the hard filter.
    scope_filter = scope if (scope and scope.get("org_id")) else None

    engine = HybridSearchEngine()
    try:
        chunks = await engine.search(
            requirement=message,
            top_k=10,
            expand=False,
            scope_filter=scope_filter,
        )
    except RetrievalUnavailable:
        # Retrieval is down. We don't want to fall through into LLM
        # synthesis -- the model would either invent an answer or
        # refuse, both of which are worse than a clear "infra is
        # down" signal. Emit a typed SSE error event so the UI can
        # render a retryable banner instead of treating it as a
        # normal turn. The pending user message is *not* committed --
        # this turn never happened from the user's history perspective.
        log.error("chat_retrieval_unavailable", conversation_id=conversation_id)
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "code": "retrieval_unavailable",
                    "message": (
                        "Search backend is currently unavailable. "
                        "Try again in a moment."
                    ),
                    "conversation_id": conversation_id,
                }
            ),
        }
        yield {"event": "done", "data": json.dumps({"conversation_id": conversation_id})}
        return

    context_parts = []
    citations = []
    for i, chunk in enumerate(chunks[:8]):
        context_parts.append(
            f"[Source {i + 1}] ({chunk.metadata.source_platform}: {chunk.metadata.source_path})\n{chunk.content[:500]}"
        )
        citations.append(
            {
                "index": i + 1,
                "source_path": chunk.metadata.source_path,
                "source_url": chunk.metadata.source_url,
                "platform": chunk.metadata.source_platform,
                "title": chunk.metadata.document_title,
                "section_heading": chunk.metadata.section_heading,
                "score": chunk.score,
                "content": chunk.content,
                "excerpt": chunk.content[:220],
            }
        )

    context = "\n\n".join(context_parts)

    # ``history`` is everything that came *before* this turn's user
    # message (which is now staged in ``pending_user_message`` instead
    # of being prepended to ``_conversations``). The ``[:-1]`` slice the
    # previous code used to drop the just-appended current message is
    # no longer needed.
    history = _conversations[conversation_id][-10:]
    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}" for msg in history
    )

    yield {
        "event": "metadata",
        "data": json.dumps({"conversation_id": conversation_id, "citations": citations}),
    }

    system_prompt = """You are PRISM, an AI assistant for platform-aware requirement analysis.
You help users understand their organization's services, teams, dependencies, and risks.

Retrieved documents are provided as GROUNDING -- use them when they are
relevant and cite with [Source N] when you do. They are NOT a cage: if the
user asks a general question the docs don't cover (e.g. "write me a python
one-liner", "explain how X algorithm works"), just answer from your own
knowledge -- don't refuse, don't ask permission, don't apologize for the
docs being off-topic.

RULES:
- Just answer the user's actual question. Never ask "would you like me to
  X" when the user has clearly already asked for X.
- Cite [Source N] only when the retrieved docs directly support the claim.
- If the user explicitly says "don't use the docs" or "general knowledge",
  skip citations entirely and answer straight from general knowledge.
- Be concise and direct. No meta-commentary about what's in the docs when
  the user didn't ask about the docs."""

    user_prompt = f"""## Retrieved Documents (grounding, cite when relevant)
{context}

## Conversation History
{history_text}

## Current Question
{message}"""

    try:
        client = get_llm_client()
        collected = ""

        stream = await client.chat.completions.create(
            model=settings.model_synthesis,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            token = chunk.choices[0].delta.content or ""
            if not token:
                continue
            collected += token
            yield {"event": "token", "data": json.dumps({"content": token})}

        # Commit the user+assistant pair atomically *after* the stream
        # finishes successfully. Staging the user message until here is
        # what keeps a failed retrieval / LLM call from leaving a
        # user-only turn behind in ``_conversations`` (which the next
        # request would then include in ``history_text``, polluting
        # the prompt context with infrastructure failures).
        _conversations[conversation_id].append(pending_user_message)
        _conversations[conversation_id].append(
            {
                "role": "assistant",
                "content": collected,
                "citations": citations,
            }
        )

    except Exception as e:
        # LLM call failed mid-stream (provider down, proxy timeout, auth
        # rejected, model overloaded, etc). The previous behavior shipped
        # the raw exception as a normal token event -- clients couldn't
        # distinguish errors from answers, and provider/proxy/model/auth
        # details leaked to the user. Emit a typed SSE error event with
        # a sanitized message; full diagnostics stay in server logs.
        # ``pending_user_message`` is intentionally never committed --
        # the failed turn doesn't shape future chat context.
        log.error(
            "chat_llm_error",
            conversation_id=conversation_id,
            error=str(e)[:500],
            error_type=type(e).__name__,
        )
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "code": "llm_unavailable",
                    "message": (
                        "Chat model is currently unavailable. "
                        "Try again in a moment."
                    ),
                    "conversation_id": conversation_id,
                }
            ),
        }

    yield {"event": "done", "data": json.dumps({"conversation_id": conversation_id})}
