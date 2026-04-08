from __future__ import annotations

import asyncio

from neo4j import AsyncGraphDatabase, AsyncDriver

from src.config import settings
from src.ingestion.team_names import canonicalize_team_name
from src.models.chunk import Chunk
from src.models.document import RawDocument
from src.observability.logging import get_logger

log = get_logger("graph_builder")

CONSTRAINTS_AND_INDEXES = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Team) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (tech:Technology) REQUIRE tech.name IS UNIQUE",
    "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.path)",
    "CREATE INDEX IF NOT EXISTS FOR (s:Service) ON (s.repo_url)",
]


class KnowledgeGraphBuilder:
    _shared_driver: AsyncDriver | None = None
    _driver_lock: asyncio.Lock | None = None
    _schema_lock: asyncio.Lock | None = None
    _initialized_keys: set[tuple[str, str]] = set()

    def __init__(self, driver: AsyncDriver, *, owns_driver: bool = False, schema_key: tuple[str, str] | None = None) -> None:
        self.driver = driver
        self.owns_driver = owns_driver
        self.schema_key = schema_key or (settings.neo4j_uri, settings.neo4j_user)

    @classmethod
    def _get_driver_lock(cls) -> asyncio.Lock:
        if cls._driver_lock is None:
            cls._driver_lock = asyncio.Lock()
        return cls._driver_lock

    @classmethod
    def _get_schema_lock(cls) -> asyncio.Lock:
        if cls._schema_lock is None:
            cls._schema_lock = asyncio.Lock()
        return cls._schema_lock

    @classmethod
    async def create(
        cls,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> KnowledgeGraphBuilder:
        uri = uri or settings.neo4j_uri
        user = user or settings.neo4j_user
        password = password or settings.neo4j_password
        use_shared_driver = (
            uri == settings.neo4j_uri
            and user == settings.neo4j_user
            and password == settings.neo4j_password
        )

        if use_shared_driver:
            if cls._shared_driver is None:
                async with cls._get_driver_lock():
                    if cls._shared_driver is None:
                        cls._shared_driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
                        log.info("graph_driver_initialized")
            driver = cls._shared_driver
        else:
            driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

        builder = cls(
            driver,
            owns_driver=not use_shared_driver,
            schema_key=(uri, user),
        )
        await builder._init_schema()
        return builder

    async def _init_schema(self) -> None:
        if self.schema_key in self._initialized_keys:
            return

        async with self._get_schema_lock():
            if self.schema_key in self._initialized_keys:
                return

            async with self.driver.session() as session:
                for statement in CONSTRAINTS_AND_INDEXES:
                    try:
                        await session.run(statement)
                    except Exception as e:
                        log.warning("schema_statement_failed", statement=statement[:80], error=str(e))

            self._initialized_keys.add(self.schema_key)
            log.info("graph_schema_initialized")

    async def add_document(self, document_id: str, doc: RawDocument) -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (d:Document {id: $id})
                SET d.title = $title,
                    d.path = $path,
                    d.platform = $platform,
                    d.last_modified = $modified,
                    d.author = $author
                """,
                id=document_id,
                title=doc.metadata.title,
                path=doc.ref.source_path,
                platform=doc.ref.source_platform,
                modified=doc.metadata.last_modified.isoformat() if doc.metadata.last_modified else None,
                author=doc.metadata.author,
            )

            if doc.metadata.author:
                await session.run(
                    """
                    MERGE (p:Person {name: $author})
                    WITH p
                    MATCH (d:Document {id: $doc_id})
                    MERGE (p)-[:AUTHORED]->(d)
                    """,
                    author=doc.metadata.author,
                    doc_id=document_id,
                )

    async def add_team(self, team_name: str, description: str = "") -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (t:Team {name: $name})
                SET t.description = CASE
                    WHEN $desc <> '' THEN $desc
                    ELSE COALESCE(t.description, '')
                END
                """,
                name=team_name,
                desc=description,
            )

    async def add_service(self, service_name: str, repo_url: str = "", team_owner: str = "") -> None:
        async with self.driver.session() as session:
            await session.run(
                "MERGE (s:Service {name: $name}) SET s.repo_url = $repo, s.team_owner = $owner",
                name=service_name,
                repo=repo_url,
                owner=team_owner,
            )

    async def add_ownership(
        self,
        team_name: str,
        service_name: str,
        confidence: str = "inferred",
        source_doc: str = "",
    ) -> list[dict]:
        async with self.driver.session() as session:
            existing = await session.run(
                """
                MATCH (t:Team)-[r:OWNS]->(s:Service {name: $service})
                RETURN t.name AS team, r.confidence AS confidence, r.source AS source
                """,
                service=service_name,
            )
            existing_records = [record.data() async for record in existing]

            conflicts = []
            for record in existing_records:
                if record["team"] != team_name:
                    conflicts.append(
                        {
                            "service": service_name,
                            "existing_team": record["team"],
                            "new_team": team_name,
                            "existing_confidence": record["confidence"],
                            "existing_source": record["source"],
                        }
                    )

            await session.run(
                """
                MERGE (t:Team {name: $team})
                MERGE (s:Service {name: $service})
                MERGE (t)-[r:OWNS]->(s)
                SET r.confidence = $conf, r.source = $src, r.last_updated = datetime()
                """,
                team=team_name,
                service=service_name,
                conf=confidence,
                src=source_doc,
            )

            if conflicts:
                log.warning(
                    "ownership_conflict",
                    service=service_name,
                    new_team=team_name,
                    existing=conflicts,
                )

            return conflicts

    async def add_dependency(self, from_service: str, to_service: str, source_doc: str = "") -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (s1:Service {name: $from})
                MERGE (s2:Service {name: $to})
                MERGE (s1)-[r:DEPENDS_ON]->(s2)
                SET r.source = $src, r.last_updated = datetime()
                """,
                **{"from": from_service},
                to=to_service,
                src=source_doc,
            )

    async def add_technology(self, service_name: str, tech_name: str) -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (s:Service {name: $service})
                MERGE (tech:Technology {name: $tech})
                MERGE (s)-[:USES]->(tech)
                """,
                service=service_name,
                tech=tech_name,
            )

    async def add_document_reference(self, document_id: str, service_name: str) -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (d:Document {id: $doc_id})
                MERGE (s:Service {name: $service})
                MERGE (d)-[:REFERENCES]->(s)
                """,
                doc_id=document_id,
                service=service_name,
            )

    async def remove_document_edges(self, document_id: str) -> None:
        async with self.driver.session() as session:
            await session.run(
                "MATCH (d:Document {id: $id})-[r]-() DELETE r",
                id=document_id,
            )

    async def query_team_services(self, team_name: str) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Team {name: $team})-[r:OWNS]->(s:Service)
                RETURN s.name AS service, r.confidence AS confidence, r.source AS source
                ORDER BY s.name
                """,
                team=team_name,
            )
            return [record.data() async for record in result]

    async def query_service_owners(self, service_name: str) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Team)-[r:OWNS]->(s:Service {name: $service})
                RETURN t.name AS team, r.confidence AS confidence, r.source AS source, r.last_updated AS updated
                ORDER BY r.last_updated DESC
                """,
                service=service_name,
            )
            return [record.data() async for record in result]

    async def query_dependencies(self, service_name: str, depth: int = 2) -> list[dict]:
        async with self.driver.session() as session:
            query = f"""
                MATCH path = (s:Service {{name: $service}})-[:DEPENDS_ON*1..{int(depth)}]->(dep:Service)
                UNWIND relationships(path) AS rel
                WITH startNode(rel) AS from_svc, endNode(rel) AS to_svc, rel
                RETURN DISTINCT from_svc.name AS from_service, to_svc.name AS to_service, rel.source AS source
                """
            result = await session.run(query, service=service_name)
            return [record.data() async for record in result]

    async def query_all_conflicts(self) -> list[dict]:
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Team)-[r:OWNS]->(s:Service)
                WITH s, COLLECT({team: t.name, confidence: r.confidence, source: r.source, updated: r.last_updated}) AS owners
                WHERE SIZE(owners) > 1
                RETURN s.name AS service, owners
                ORDER BY s.name
                """
            )
            return [record.data() async for record in result]

    async def sanitize_team_nodes(self) -> dict[str, int]:
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Team)
                OPTIONAL MATCH (t)-[r:OWNS]->(s:Service)
                RETURN t.name AS name, t.description AS description,
                       COLLECT({service: s.name, confidence: r.confidence, source: r.source}) AS ownerships
                """
            )
            team_rows = [record.data() async for record in result]

        merged = 0
        removed_invalid = 0

        for row in team_rows:
            raw_name = row.get("name", "")
            canonical = canonicalize_team_name(raw_name)
            ownerships = [
                ownership
                for ownership in row.get("ownerships", [])
                if ownership and ownership.get("service")
            ]

            if not canonical:
                if not ownerships:
                    await self._delete_team(raw_name)
                    removed_invalid += 1
                else:
                    log.warning("invalid_team_with_ownership_retained", team=raw_name, ownerships=ownerships)
                continue

            if canonical == raw_name:
                continue

            await self.add_team(canonical, row.get("description", "") or "")
            for ownership in ownerships:
                await self.add_ownership(
                    canonical,
                    ownership.get("service", ""),
                    ownership.get("confidence") or "inferred",
                    ownership.get("source") or "",
                )
            await self._delete_team(raw_name)
            merged += 1

        if merged or removed_invalid:
            log.info("team_nodes_sanitized", merged=merged, removed_invalid=removed_invalid)

        return {"merged": merged, "removed_invalid": removed_invalid}

    async def _delete_team(self, team_name: str) -> None:
        async with self.driver.session() as session:
            await session.run(
                "MATCH (t:Team {name: $name}) DETACH DELETE t",
                name=team_name,
            )

    async def close(self) -> None:
        if self.owns_driver:
            await self.driver.close()

    @classmethod
    async def shutdown_shared(cls) -> None:
        if cls._shared_driver is None:
            return

        async with cls._get_driver_lock():
            if cls._shared_driver is not None:
                await cls._shared_driver.close()
                cls._shared_driver = None
                cls._initialized_keys.clear()
                log.info("graph_driver_closed")
