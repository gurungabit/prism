"""CRUD for ``services`` + graph helpers that used to live on KnowledgeStore."""

from __future__ import annotations

from uuid import UUID

from src.catalog.base_repo import CatalogRepo
from src.catalog.models import Service


class ServiceRepository(CatalogRepo):
    async def list_for_team(self, team_id: UUID) -> list[Service]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, team_id, name, repo_url, description, created_at
                FROM services
                WHERE team_id = $1
                ORDER BY name
                """,
                team_id,
            )
            return [Service.model_validate(dict(r)) for r in rows]

    async def list_all(self) -> list[Service]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, team_id, name, repo_url, description, created_at
                FROM services
                ORDER BY name
                """
            )
            return [Service.model_validate(dict(r)) for r in rows]

    async def get(self, service_id: UUID) -> Service | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, team_id, name, repo_url, description, created_at
                FROM services
                WHERE id = $1
                """,
                service_id,
            )
            return Service.model_validate(dict(row)) if row else None

    async def get_by_name(self, team_id: UUID, name: str) -> Service | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, team_id, name, repo_url, description, created_at
                FROM services
                WHERE team_id = $1 AND name = $2
                """,
                team_id,
                name,
            )
            return Service.model_validate(dict(row)) if row else None

    async def find_any_by_name(self, name: str) -> Service | None:
        """Find a service by name across the whole org, regardless of team.

        Used by dependency reconciliation to turn a free-text name in a
        document into a declared service reference. Name collisions across
        teams return the first match (plan open question 1 keeps names
        team-scoped, so collisions should be rare in practice).
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, team_id, name, repo_url, description, created_at
                FROM services
                WHERE name = $1
                ORDER BY created_at
                LIMIT 1
                """,
                name,
            )
            return Service.model_validate(dict(row)) if row else None

    async def insert(
        self,
        team_id: UUID,
        name: str,
        repo_url: str = "",
        description: str = "",
    ) -> Service:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO services (team_id, name, repo_url, description)
                VALUES ($1, $2, $3, $4)
                RETURNING id, team_id, name, repo_url, description, created_at
                """,
                team_id,
                name,
                repo_url,
                description,
            )
            return Service.model_validate(dict(row))

    async def update(
        self,
        service_id: UUID,
        *,
        name: str | None = None,
        repo_url: str | None = None,
        description: str | None = None,
    ) -> Service | None:
        sets = []
        args: list = []
        idx = 2
        if name is not None:
            sets.append(f"name = ${idx}")
            args.append(name)
            idx += 1
        if repo_url is not None:
            sets.append(f"repo_url = ${idx}")
            args.append(repo_url)
            idx += 1
        if description is not None:
            sets.append(f"description = ${idx}")
            args.append(description)
            idx += 1

        if not sets:
            return await self.get(service_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE services SET {', '.join(sets)}
                WHERE id = $1
                RETURNING id, team_id, name, repo_url, description, created_at
                """,
                service_id,
                *args,
            )
            return Service.model_validate(dict(row)) if row else None

    async def delete(self, service_id: UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM services WHERE id = $1",
                service_id,
            )
            return result.endswith(" 1")

    # ----- dependency graph helpers -----

    async def add_dependency(
        self,
        from_service_id: UUID,
        to_service_id: UUID,
        source_doc: str = "",
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_dependencies (from_service_id, to_service_id, source, last_updated)
                VALUES ($1, $2, $3, now())
                ON CONFLICT (from_service_id, to_service_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    last_updated = now()
                """,
                from_service_id,
                to_service_id,
                source_doc,
            )

    async def add_pending_dependency(
        self,
        from_service_id: UUID,
        to_service_name: str,
        source_doc: str = "",
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_pending_dependencies (from_service_id, to_service_name, source_doc)
                VALUES ($1, $2, $3)
                ON CONFLICT (from_service_id, to_service_name) DO UPDATE SET
                    source_doc = EXCLUDED.source_doc
                """,
                from_service_id,
                to_service_name,
                source_doc,
            )

    async def reconcile_pending_dependencies(self, service_id: UUID, service_name: str) -> int:
        """When a service is declared, promote any pending edges pointing at
        ``service_name`` into real dependencies.

        Returns the number of edges reconciled.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT from_service_id, source_doc
                    FROM kg_pending_dependencies
                    WHERE to_service_name = $1
                    """,
                    service_name,
                )
                if not rows:
                    return 0

                for row in rows:
                    await conn.execute(
                        """
                        INSERT INTO kg_dependencies (from_service_id, to_service_id, source, last_updated)
                        VALUES ($1, $2, $3, now())
                        ON CONFLICT (from_service_id, to_service_id) DO UPDATE SET
                            source = EXCLUDED.source,
                            last_updated = now()
                        """,
                        row["from_service_id"],
                        service_id,
                        row["source_doc"],
                    )

                await conn.execute(
                    "DELETE FROM kg_pending_dependencies WHERE to_service_name = $1",
                    service_name,
                )
                return len(rows)

    async def list_all_dependencies(self) -> list[dict]:
        """Every declared edge in ``kg_dependencies`` with resolved names.

        Used by the org-graph endpoint to render the full service dependency
        network in one call -- cheaper than hitting per-service endpoints for
        N services.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.from_service_id, d.to_service_id, d.source,
                       s_from.name AS from_service,
                       s_to.name   AS to_service
                FROM kg_dependencies d
                JOIN services s_from ON s_from.id = d.from_service_id
                JOIN services s_to   ON s_to.id   = d.to_service_id
                """
            )
            return [
                {
                    "from_service_id": str(r["from_service_id"]),
                    "to_service_id": str(r["to_service_id"]),
                    "from_service": r["from_service"],
                    "to_service": r["to_service"],
                    "source": r["source"],
                }
                for r in rows
            ]

    async def query_dependencies(self, service_id: UUID, depth: int = 2) -> list[dict]:
        """Walk outbound dependencies up to ``depth`` hops.

        Returns rows with resolved service names so the API surface doesn't
        force every caller to join back to ``services``.
        """
        depth = max(1, min(int(depth), 20))
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH RECURSIVE walk AS (
                    SELECT from_service_id, to_service_id, source, 1 AS depth
                    FROM kg_dependencies
                    WHERE from_service_id = $1
                    UNION
                    SELECT d.from_service_id, d.to_service_id, d.source, walk.depth + 1
                    FROM kg_dependencies d
                    JOIN walk ON d.from_service_id = walk.to_service_id
                    WHERE walk.depth < $2
                )
                SELECT DISTINCT
                    walk.from_service_id,
                    walk.to_service_id,
                    walk.source,
                    s_from.name AS from_service,
                    s_to.name   AS to_service
                FROM walk
                JOIN services s_from ON s_from.id = walk.from_service_id
                JOIN services s_to   ON s_to.id   = walk.to_service_id
                """,
                service_id,
                depth,
            )
            return [
                {
                    "from_service_id": str(r["from_service_id"]),
                    "to_service_id": str(r["to_service_id"]),
                    "from_service": r["from_service"],
                    "to_service": r["to_service"],
                    "source": r["source"],
                }
                for r in rows
            ]
