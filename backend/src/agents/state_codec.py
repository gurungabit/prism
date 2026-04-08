from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.agents.result import AgentResult
from src.models.chunk import Chunk


def checkpoint_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, BaseModel):
        return checkpoint_safe(value.model_dump(mode="json"))

    if isinstance(value, Mapping):
        return {str(key): checkpoint_safe(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [checkpoint_safe(item) for item in value]

    if isinstance(value, set):
        return [checkpoint_safe(item) for item in value]

    if isinstance(value, datetime | date | time):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="replace")

    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except TypeError:
            pass

    return str(value)


def checkpoint_safe_update(update: dict[str, Any]) -> dict[str, Any]:
    return checkpoint_safe(update)


def normalize_chunks(value: Any) -> list[Chunk]:
    if not value:
        return []

    chunks: list[Chunk] = []
    for item in value:
        if isinstance(item, Chunk):
            chunks.append(item)
            continue
        if isinstance(item, dict):
            chunks.append(Chunk.model_validate(item))
    return chunks


def normalize_agent_result(value: Any) -> AgentResult | None:
    if value is None:
        return None
    if isinstance(value, AgentResult):
        return value
    if isinstance(value, dict):
        return AgentResult.model_validate(value)
    return None
