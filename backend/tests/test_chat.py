"""Chat stream tests.

These tests exercise ``chat_stream`` directly -- they're sync wrappers
around the async generator that drive it through retrieval / LLM
failure branches without spinning up the full FastAPI app. Stubs the
search engine + LLM client so no network or DB is required.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest

from src.api import chat as chat_module
from src.api.chat import chat_stream
from src.retrieval.hybrid_search import RetrievalUnavailable


@pytest.fixture(autouse=True)
def _clean_conversations():
    """Reset the conversation store between tests so state doesn't
    bleed across cases. ``conversation_store.clear`` wipes both
    halves (messages + ``updated_at``) atomically.
    """
    chat_module.conversation_store.clear()
    yield
    chat_module.conversation_store.clear()


async def _drain(gen):
    """Collect every event the generator yields (parsed as dicts)."""
    events = []
    async for ev in gen:
        events.append(ev)
    return events


def test_retrieval_failure_does_not_pollute_conversation_history():
    """Regression: a user message used to be appended to ``_conversations``
    *before* retrieval ran, so a retrieval outage left a user-only turn
    behind. The next turn would then include that orphan in
    ``history_text`` (and the conversation preview), making
    infrastructure failures shape future chat context.

    The fix stages the user message locally and only commits it after
    the assistant response finishes. After a failed turn,
    ``_conversations[conv_id]`` should be empty.
    """
    conv_id = "conv-retrieval-fail"

    async def _fake_search(*_args: Any, **_kwargs: Any) -> Any:
        raise RetrievalUnavailable("simulated OpenSearch outage")

    async def _run():
        with patch.object(
            chat_module.HybridSearchEngine, "search", side_effect=_fake_search
        ):
            events = await _drain(
                chat_stream("hello world", conversation_id=conv_id)
            )
        return events

    events = asyncio.run(_run())

    # Should have emitted exactly: error event, done event.
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) == 1
    payload = json.loads(error_events[0]["data"])
    assert payload["code"] == "retrieval_unavailable"
    assert payload["conversation_id"] == conv_id

    # And critically: the user message was *not* committed to history.
    # No other request can pull this orphan into its prompt context.
    # ``store.get`` returns None when the conversation was never
    # persisted; the list endpoint also won't surface a phantom
    # "Today" conversation since updated_at lives on the same store.
    assert chat_module.conversation_store.get(conv_id) is None
    listed = [c["conversation_id"] for c in chat_module.conversation_store.list()]
    assert conv_id not in listed


def test_llm_failure_does_not_pollute_conversation_history():
    """Same regression on the LLM-failure branch: the user message is
    only committed alongside a successful assistant response. An LLM
    outage mid-stream emits a typed ``llm_unavailable`` SSE event and
    leaves ``_conversations`` untouched.
    """
    conv_id = "conv-llm-fail"

    async def _fake_search(*_args: Any, **_kwargs: Any) -> list:
        return []  # retrieval succeeds with zero hits

    class _BoomLLM:
        async def chat_completions_create(self, **_):  # noqa: ANN001
            raise RuntimeError("simulated upstream LLM 500")

    class _Client:
        class chat:  # type: ignore[no-redef]
            class completions:  # type: ignore[no-redef]
                @staticmethod
                async def create(**_):  # noqa: ANN001
                    raise RuntimeError("simulated upstream LLM 500")

    async def _run():
        with patch.object(
            chat_module.HybridSearchEngine, "search", side_effect=_fake_search
        ), patch.object(chat_module, "get_llm_client", return_value=_Client()):
            return await _drain(
                chat_stream("a question", conversation_id=conv_id)
            )

    events = asyncio.run(_run())

    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) == 1
    payload = json.loads(error_events[0]["data"])
    assert payload["code"] == "llm_unavailable"
    # Sanitized message -- raw exception text must not leak through.
    assert "simulated upstream LLM 500" not in payload["message"]

    # User message stays out of history -- this turn never happened.
    assert chat_module.conversation_store.get(conv_id) is None
    listed = [c["conversation_id"] for c in chat_module.conversation_store.list()]
    assert conv_id not in listed


def test_successful_turn_commits_user_and_assistant_pair():
    """Sanity check on the happy path: a successful stream commits both
    the user message and the assistant message in order. The pair is
    atomic -- if the regression came back, the user message would
    appear before retrieval ran instead of after the stream finished.
    """
    conv_id = "conv-happy"

    async def _fake_search(*_args: Any, **_kwargs: Any) -> list:
        return []

    class _Stream:
        def __init__(self):
            self._chunks = [
                _make_token_chunk("hello "),
                _make_token_chunk("world"),
            ]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class _Client:
        class chat:  # type: ignore[no-redef]
            class completions:  # type: ignore[no-redef]
                @staticmethod
                async def create(**_):  # noqa: ANN001
                    return _Stream()

    async def _run():
        with patch.object(
            chat_module.HybridSearchEngine, "search", side_effect=_fake_search
        ), patch.object(chat_module, "get_llm_client", return_value=_Client()):
            return await _drain(
                chat_stream("greet me", conversation_id=conv_id)
            )

    asyncio.run(_run())

    history = chat_module.conversation_store.get(conv_id) or []
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "greet me"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "hello world"
    # ``commit_pair`` stamps ``updated_at`` atomically with the
    # message append, so the list endpoint surfaces this row with
    # a real timestamp (not a placeholder).
    listed = chat_module.conversation_store.list()
    row = next((r for r in listed if r["conversation_id"] == conv_id), None)
    assert row is not None
    assert row["updated_at"] is not None


def _make_token_chunk(text: str):
    """Minimal stub matching the OpenAI streaming chunk shape:
    ``chunk.choices[0].delta.content``."""

    class _Delta:
        content = text

    class _Choice:
        delta = _Delta()

    class _Chunk:
        choices = [_Choice()]

    return _Chunk()
