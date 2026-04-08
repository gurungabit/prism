from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class AgentResult(BaseModel):
    status: Literal["success", "partial", "failed"]
    data: Any = None
    error: str | None = None
    degradation_note: str | None = None
