from __future__ import annotations

from src.ingestion.graph_builder import KnowledgeGraphBuilder
from src.observability.logging import get_logger

log = get_logger("graph_search")


async def get_team_profile(graph: KnowledgeGraphBuilder, team_name: str) -> dict:
    services = await graph.query_team_services(team_name)
    return {
        "team": team_name,
        "services": services,
        "service_count": len(services),
    }


async def get_service_dependencies(
    graph: KnowledgeGraphBuilder,
    service_name: str,
    depth: int = 2,
) -> list[dict]:
    return await graph.query_dependencies(service_name, depth)


async def get_service_ownership(
    graph: KnowledgeGraphBuilder,
    service_name: str,
) -> list[dict]:
    return await graph.query_service_owners(service_name)


async def find_related_services(
    graph: KnowledgeGraphBuilder,
    service_names: list[str],
    depth: int = 2,
) -> dict[str, list[dict]]:
    result = {}
    for service in service_names:
        deps = await get_service_dependencies(graph, service, depth)
        result[service] = deps
    return result


async def get_all_teams(graph: KnowledgeGraphBuilder) -> list[dict]:
    async with graph.driver.session() as session:
        result = await session.run(
            """
            MATCH (t:Team)
            OPTIONAL MATCH (t)-[:OWNS]->(s:Service)
            RETURN t.name AS team, t.description AS description, COLLECT(s.name) AS services
            ORDER BY t.name
            """
        )
        return [record.data() async for record in result]


async def get_all_conflicts(graph: KnowledgeGraphBuilder) -> list[dict]:
    return await graph.query_all_conflicts()
