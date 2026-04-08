from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from typing import Any, AsyncGenerator

from src.observability.logging import get_logger

log = get_logger("streaming")


class AnalysisEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = defaultdict(list)
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._complete: set[str] = set()

    def _generate_event_id(self, analysis_id: str) -> str:
        seq = len(self._events[analysis_id])
        return f"{analysis_id}-{seq:06d}"

    async def publish(self, analysis_id: str, event: dict) -> None:
        event_id = self._generate_event_id(analysis_id)
        event["id"] = event_id
        event["timestamp"] = time.time()
        self._events[analysis_id].append(event)

        for queue in self._subscribers.get(analysis_id, []):
            await queue.put(event)

    async def publish_complete(self, analysis_id: str, report: dict) -> None:
        await self.publish(
            analysis_id,
            {
                "type": "complete",
                "report": report,
            },
        )
        self._complete.add(analysis_id)

        for queue in self._subscribers.get(analysis_id, []):
            await queue.put(None)

    def subscribe(self, analysis_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[analysis_id].append(queue)
        return queue

    def unsubscribe(self, analysis_id: str, queue: asyncio.Queue) -> None:
        if analysis_id in self._subscribers:
            try:
                self._subscribers[analysis_id].remove(queue)
            except ValueError:
                pass

    def get_events_after(self, analysis_id: str, last_event_id: str | None) -> list[dict]:
        events = self._events.get(analysis_id, [])
        if not last_event_id:
            return events

        for i, event in enumerate(events):
            if event.get("id") == last_event_id:
                return events[i + 1 :]

        return events

    def is_complete(self, analysis_id: str) -> bool:
        return analysis_id in self._complete

    def get_all_events(self, analysis_id: str) -> list[dict]:
        return self._events.get(analysis_id, [])


event_store = AnalysisEventStore()


def create_step_callback(analysis_id: str):
    async def on_step(step_data: dict) -> None:
        await event_store.publish(
            analysis_id,
            {
                "type": "agent_step",
                "agent": step_data.get("agent", "unknown"),
                "action": step_data.get("action", ""),
                "detail": step_data.get("detail", ""),
                "data": step_data.get("data"),
            },
        )

    return on_step


async def stream_events(
    analysis_id: str,
    last_event_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    replay_events = event_store.get_events_after(analysis_id, last_event_id)
    for event in replay_events:
        yield _to_sse_dict(event)

    if event_store.is_complete(analysis_id):
        return

    queue = event_store.subscribe(analysis_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                if event is None:
                    break
                yield _to_sse_dict(event)
            except asyncio.TimeoutError:
                yield {"comment": "keepalive"}
    finally:
        event_store.unsubscribe(analysis_id, queue)


def _to_sse_dict(event: dict) -> dict:
    return {
        "id": event.get("id", ""),
        "data": json.dumps(event, default=str),
    }
