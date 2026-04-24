from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import AsyncGenerator

from src.config import settings
from src.llm_client import get_llm_client
from src.observability.logging import get_logger
from src.retrieval.hybrid_search import HybridSearchEngine

log = get_logger("chat")

_conversations: dict[str, list[dict]] = defaultdict(list)


async def chat_stream(
    message: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    conversation_id = conversation_id or str(uuid.uuid4())

    _conversations[conversation_id].append({"role": "user", "content": message})

    engine = HybridSearchEngine()
    chunks = await engine.search(
        requirement=message,
        top_k=10,
        expand=False,
    )

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

    history = _conversations[conversation_id][-10:]
    history_text = "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in history[:-1])

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

        _conversations[conversation_id].append(
            {
                "role": "assistant",
                "content": collected,
                "citations": citations,
            }
        )

    except Exception as e:
        log.error("chat_error", error=str(e))
        error_msg = f"Error: {e}"
        _conversations[conversation_id].append({"role": "assistant", "content": error_msg})
        yield {"event": "token", "data": json.dumps({"content": error_msg})}

    yield {"event": "done", "data": json.dumps({"conversation_id": conversation_id})}
