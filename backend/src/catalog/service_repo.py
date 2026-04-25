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
                INSERT INTO kg_dependencies (
                    from_service_id, to_service_id, source, last_updated
                )
                VALUES ($1, $2, $3, now())
                ON CONFLICT (from_service_id, to_service_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    last_updated = now()
                """,
                from_service_id,
                to_service_id,
                source_doc,
            )

    async def add_external_dependency(
        self,
        from_service_id: UUID,
        external_name: str,
        external_description: str = "",
        source_doc: str = "manual",
    ) -> None:
        """Edge to a target outside the declared catalog (Stripe, Auth0, an
        upstream team's API, etc.). Identified by free-text name; the row
        carries an optional description but no service_id.

        Uniqueness is case-insensitive (``Stripe`` and ``stripe`` collide).
        The display name keeps whatever casing the caller provided -- the
        ``ON CONFLICT`` target references the function-based unique index
        ``kg_dependencies_external_name_lower_uniq``, so re-adding with a
        different casing updates the existing row's description in place.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_dependencies (
                    from_service_id, to_external_name, to_external_description,
                    source, last_updated
                )
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (from_service_id, (lower(to_external_name))) WHERE to_external_name IS NOT NULL
                DO UPDATE SET
                    to_external_description = EXCLUDED.to_external_description,
                    source = EXCLUDED.source,
                    last_updated = now()
                """,
                from_service_id,
                external_name,
                external_description,
                source_doc,
            )

    async def remove_dependency(
        self,
        from_service_id: UUID,
        to_service_id: UUID,
    ) -> bool:
        """Remove an internal (catalog) edge."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM kg_dependencies
                WHERE from_service_id = $1 AND to_service_id = $2
                """,
                from_service_id,
                to_service_id,
            )
            return result.endswith(" 1")

    async def remove_external_dependency(
        self,
        from_service_id: UUID,
        external_name: str,
    ) -> bool:
        """Remove an external (free-text) dep, matched case-insensitively
        against ``to_external_name``. Mirrors the case-insensitive uniqueness
        on insert so the UI can pass back whatever casing the user typed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM kg_dependencies
                WHERE from_service_id = $1
                  AND to_external_name IS NOT NULL
                  AND lower(to_external_name) = lower($2)
                """,
                from_service_id,
                external_name,
            )
            return result.endswith(" 1")

    async def list_outbound_dependencies(self, from_service_id: UUID) -> list[dict]:
        """Edges (internal + external) where ``from_service_id`` is the
        source. Powers the service detail page's Dependencies section.

        Each row carries a ``kind`` of ``"service"`` (linked to a declared
        service) or ``"external"`` (free-text target outside the catalog).
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT d.to_service_id,
                       d.to_external_name,
                       d.to_external_description,
                       d.source,
                       d.last_updated,
                       s.name    AS svc_name,
                       s.team_id AS svc_team_id,
                       t.name    AS team_name
                FROM kg_dependencies d
                LEFT JOIN services s ON s.id = d.to_service_id
                LEFT JOIN teams t    ON t.id = s.team_id
                WHERE d.from_service_id = $1
                ORDER BY COALESCE(s.name, d.to_external_name) ASC
                """,
                from_service_id,
            )
            out: list[dict] = []
            for r in rows:
                if r["to_service_id"] is not None:
                    out.append(
                        {
                            "kind": "service",
                            "to_service_id": str(r["to_service_id"]),
                            "to_service_name": r["svc_name"],
                            "team_id": str(r["svc_team_id"]) if r["svc_team_id"] else None,
                            "team_name": r["team_name"],
                            "description": "",
                            "source": r["source"],
                            "last_updated": r["last_updated"].isoformat() if r["last_updated"] else None,
                        }
                    )
                else:
                    out.append(
                        {
                            "kind": "external",
                            "to_service_id": None,
                            "to_service_name": r["to_external_name"],
                            "team_id": None,
                            "team_name": None,
                            "description": r["to_external_description"] or "",
                            "source": r["source"],
                            "last_updated": r["last_updated"].isoformat() if r["last_updated"] else None,
                        }
                    )
            return out

    async def list_all_dependencies(self) -> list[dict]:
        """Every internal edge in ``kg_dependencies`` with resolved names.

        Used by the org-graph endpoint to render the full service dependency
        network in one call -- cheaper than hitting per-service endpoints for
        N services. External-target edges are excluded because the org graph
        only renders nodes for declared catalog entities.
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
                WHERE d.to_service_id IS NOT NULL
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
