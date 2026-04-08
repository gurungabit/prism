from __future__ import annotations

from ollama import AsyncClient

from src.config import settings

_client: AsyncClient | None = None


def get_ollama_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient(host=settings.ollama_host)
    return _client
