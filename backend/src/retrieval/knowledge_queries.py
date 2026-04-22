"""Thin query layer the agents call into.

Previously these helpers wrapped ``KnowledgeStore`` methods that joined the
inferred ``kg_teams``/``kg_services``/``kg_ownership`` tables. Under the
declared model those joins become direct reads against the catalog. The
function signatures stay similar so the agents (``router_agent``,
``dependency_agent``) don't need a full rewrite -- they receive dicts shaped
the same way.

Conflict reporting is dropped entirely in Phase 1 (plan open question 4):
under the declared model a service has exactly one team, so ownership
conflicts can't occur at the data layer.
"""

from __future__ import annotations

from src.catalog import ServiceRepository, TeamRepository
from src.observability.logging import get_logger

log = get_logger("knowledge_queries")


async def get_all_teams(team_repo: TeamRepository, service_repo: ServiceRepository) -> list[dict]:
    """Return the same ``[{team, description, services}]`` shape the old code emitted.

    The router agent expects to see declared teams with their owned services
    so it can pick the right primary/supporting team for a requirement.
    """
    teams = await team_repo.list_all()
    services = await service_repo.list_all()

    services_by_team: dict[str, list[str]] = {}
    for svc in services:
        services_by_team.setdefault(str(svc.team_id), []).append(svc.name)

    return [
        {
            "team": t.name,
            "team_id": str(t.id),
            "org_id": str(t.org_id),
            "description": t.description or "",
            "services": sorted(services_by_team.get(str(t.id), [])),
        }
        for t in teams
    ]


async def get_team_profile(
    team_repo: TeamRepository,
    service_repo: ServiceRepository,
    team_name: str,
) -> dict:
    # Names are unique within an org; we don't know the org here, so we pick
    # the first match. Real multi-org work is Phase 3.
    teams = await team_repo.list_all()
    match = next((t for t in teams if t.name == team_name), None)
    if match is None:
        return {"team": team_name, "services": [], "service_count": 0}

    services = await service_repo.list_for_team(match.id)
    return {
        "team": team_name,
        "team_id": str(match.id),
        "org_id": str(match.org_id),
        "description": match.description,
        "services": [
            {
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "repo_url": s.repo_url,
            }
            for s in services
        ],
        "service_count": len(services),
    }


async def get_service_dependencies(
    service_repo: ServiceRepository,
    service_name: str,
    depth: int = 2,
) -> list[dict]:
    """Resolve a service name to an id, then walk outbound dependencies."""
    service = await service_repo.find_any_by_name(service_name)
    if service is None:
        return []
    return await service_repo.query_dependencies(service.id, depth=depth)


async def find_related_services(
    service_repo: ServiceRepository,
    service_names: list[str],
    depth: int = 2,
) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for name in service_names:
        result[name] = await get_service_dependencies(service_repo, name, depth=depth)
    return result


async def get_service_ownership(
    team_repo: TeamRepository,
    service_repo: ServiceRepository,
    service_name: str,
) -> list[dict]:
    """Return the declared team for each service with that name.

    Under the declared model there's always exactly one owner per service
    (plan open question 1). Returning a list keeps the API shape compatible
    with the old conflict-aware endpoint.
    """
    services = await service_repo.list_all()
    matches = [s for s in services if s.name == service_name]
    if not matches:
        return []

    teams = {str(t.id): t for t in await team_repo.list_all()}
    return [
        {
            "team": teams[str(s.team_id)].name if str(s.team_id) in teams else str(s.team_id),
            "team_id": str(s.team_id),
            "service_id": str(s.id),
            "confidence": "declared",
            "source": "catalog",
        }
        for s in matches
    ]
