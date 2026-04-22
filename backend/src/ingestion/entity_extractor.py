from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from src.config import settings
from src.ingestion.team_names import canonicalize_team_name, extract_explicit_team_names
from src.llm_client import get_llm_client
from src.observability.logging import get_logger

log = get_logger("entity_extractor")


class ExtractedEntities(BaseModel):
    teams: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    technologies: list[str] = []
    dependencies: list[dict[str, str]] = []


EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured entity information from technical documents. "
    "Return ONLY teams, services, technologies, and dependencies you find explicitly mentioned. "
    "Do NOT infer or guess — only extract what is clearly stated."
)

EXTRACTION_USER_TEMPLATE = """Extract team names, service names, dependencies between services, and technologies from this document.

For teams, include what services they own if mentioned.
For services, include what they depend on if mentioned.
For technologies, list frameworks, languages, databases, tools mentioned.

Document title: {title}
Source: {source_path}

Content (first 3000 chars):
{content}"""


async def extract_entities(
    content: str,
    title: str = "",
    source_path: str = "",
) -> ExtractedEntities:
    try:
        prompt = EXTRACTION_USER_TEMPLATE.format(
            title=title,
            source_path=source_path,
            content=content[:3000],
        )

        schema_hint = json.dumps(ExtractedEntities.model_json_schema(), separators=(",", ":"))
        structured_system = (
            f"{EXTRACTION_SYSTEM_PROMPT}\n\n"
            f"Respond with a single JSON object matching this schema:\n{schema_hint}\n"
            "Return ONLY the JSON object — no prose, no code fences."
        )

        client = get_llm_client()
        response = await client.chat.completions.create(
            model=settings.model_bulk,
            messages=[
                {"role": "system", "content": structured_system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        content_text = response.choices[0].message.content or ""
        parsed = json.loads(content_text)
        entities = ExtractedEntities.model_validate(parsed)
        return _normalize_entities(entities, content, source_path)

    except Exception as e:
        log.warning("entity_extraction_failed_using_regex", error=str(e)[:100], source=source_path)
        return _regex_fallback(content, source_path)


def _normalize_entities(
    entities: ExtractedEntities,
    content: str,
    source_path: str,
) -> ExtractedEntities:
    merged_teams: dict[str, dict[str, Any]] = {}

    for team in entities.teams:
        raw_name = str(team.get("name", ""))
        canonical = canonicalize_team_name(raw_name)
        if not canonical:
            continue

        team_entry = merged_teams.setdefault(canonical.lower(), {"name": canonical, "owns": []})
        for service in team.get("owns", []):
            service_name = str(service).strip()
            if service_name and service_name not in team_entry["owns"]:
                team_entry["owns"].append(service_name)

    for explicit_team in extract_explicit_team_names(content, source_path):
        merged_teams.setdefault(explicit_team.lower(), {"name": explicit_team, "owns": []})

    return ExtractedEntities(
        teams=list(merged_teams.values()),
        services=entities.services,
        technologies=entities.technologies,
        dependencies=entities.dependencies,
    )


def _regex_fallback(content: str, source_path: str = "") -> ExtractedEntities:
    services = list(set(re.findall(r"\b(\w+[-_](?:service|api|gateway|worker|processor))\b", content.lower())))
    teams = extract_explicit_team_names(content, source_path)

    return ExtractedEntities(
        teams=[{"name": team, "owns": []} for team in teams],
        services=[{"name": s, "depends_on": []} for s in services],
        technologies=[],
        dependencies=[],
    )
