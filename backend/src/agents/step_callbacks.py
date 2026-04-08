from __future__ import annotations

from collections.abc import Awaitable, Callable

StepCallback = Callable[[dict], Awaitable[None]]

_callbacks: dict[str, StepCallback] = {}


def register_step_callback(analysis_id: str, callback: StepCallback) -> None:
    _callbacks[analysis_id] = callback


def get_step_callback(analysis_id: str | None) -> StepCallback | None:
    if not analysis_id:
        return None
    return _callbacks.get(analysis_id)


def clear_step_callback(analysis_id: str | None) -> None:
    if not analysis_id:
        return
    _callbacks.pop(analysis_id, None)
