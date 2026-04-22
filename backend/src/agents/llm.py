from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from src.llm_client import get_llm_client
from src.observability.logging import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)


async def llm_call(
    prompt: str,
    system_prompt: str,
    output_schema: type[T],
    model: str = "gpt-5-mini",
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

    schema_hint = json.dumps(output_schema.model_json_schema(), separators=(",", ":"))
    structured_system = (
        f"{system_prompt}\n\n"
        f"Respond with a single JSON object that conforms to this schema:\n{schema_hint}\n"
        "Return ONLY the JSON object — no prose, no code fences."
    )

    try:
        client = get_llm_client()

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": structured_system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""

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
