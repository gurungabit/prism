from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from src.config import settings
from src.ollama_client import get_ollama_client
from src.observability.logging import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)


async def llm_call(
    prompt: str,
    system_prompt: str,
    output_schema: type[T],
    model: str = "qwen2.5:7b",
    max_turns: int = 1,
    agent_name: str = "unknown",
    analysis_id: str = "unknown",
    on_step: Any = None,
) -> T:
    log.info(
        "llm_call_start",
        agent=agent_name,
        analysis_id=analysis_id,
        model=model,
        schema=output_schema.__name__,
    )

    if on_step:
        await on_step({"agent": agent_name, "action": "reasoning", "detail": "AI is analyzing..."})

    try:
        client = get_ollama_client()

        response = await client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            format=output_schema.model_json_schema(),
        )

        content = response["message"]["content"]

        if on_step:
            await on_step({"agent": agent_name, "action": "llm_complete"})

        parsed = json.loads(content)
        result = output_schema.model_validate(parsed)
        log.info("llm_call_complete", agent=agent_name, analysis_id=analysis_id)
        return result

    except (json.JSONDecodeError, ValueError) as e:
        log.error("llm_response_parse_failed", agent=agent_name, error=str(e))
        if on_step:
            await on_step({"agent": agent_name, "action": "error", "detail": f"Failed to parse response: {str(e)[:100]}"})
        raise
    except Exception as e:
        log.error("llm_call_failed", agent=agent_name, error=str(e))
        if on_step:
            await on_step({"agent": agent_name, "action": "error", "detail": f"LLM call failed: {str(e)[:100]}"})
        raise
