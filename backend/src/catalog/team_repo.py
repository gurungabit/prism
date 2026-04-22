"""CRUD for ``teams``."""

from __future__ import annotations

from uuid import UUID

from src.catalog.base_repo import CatalogRepo
from src.catalog.models import Team


class TeamRepository(CatalogRepo):
    async def list_for_org(self, org_id: UUID) -> list[Team]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, org_id, name, description, created_at
                FROM teams
                WHERE org_id = $1
                ORDER BY name
                """,
                org_id,
            )
            return [Team.model_validate(dict(r)) for r in rows]

    async def list_all(self) -> list[Team]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, org_id, name, description, created_at
                FROM teams
                ORDER BY name
                """
            )
            return [Team.model_validate(dict(r)) for r in rows]

    async def get(self, team_id: UUID) -> Team | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, org_id, name, description, created_at
                FROM teams WHERE id = $1
                """,
                team_id,
            )
            return Team.model_validate(dict(row)) if row else None

    async def insert(self, org_id: UUID, name: str, description: str = "") -> Team:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO teams (org_id, name, description)
                VALUES ($1, $2, $3)
                RETURNING id, org_id, name, description, created_at
                """,
                org_id,
                name,
                description,
            )
            return Team.model_validate(dict(row))

    async def update(
        self,
        team_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Team | None:
        # Build an UPDATE only over the fields actually provided so we don't
        # clobber description with '' when the caller only sends name.
        sets = []
        args: list = []
        idx = 2  # $1 is reserved for team_id
        if name is not None:
            sets.append(f"name = ${idx}")
            args.append(name)
            idx += 1
        if description is not None:
            sets.append(f"description = ${idx}")
            args.append(description)
            idx += 1

        if not sets:
            return await self.get(team_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE teams SET {', '.join(sets)}
                WHERE id = $1
                RETURNING id, org_id, name, description, created_at
                """,
                team_id,
                *args,
            )
            return Team.model_validate(dict(row)) if row else None

    async def delete(self, team_id: UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM teams WHERE id = $1",
                team_id,
            )
            return result.endswith(" 1")

    async def get_by_name(self, org_id: UUID, name: str) -> Team | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, org_id, name, description, created_at
                FROM teams
                WHERE org_id = $1 AND name = $2
                """,
                org_id,
                name,
            )
            return Team.model_validate(dict(row)) if row else None
