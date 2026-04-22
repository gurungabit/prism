"""CRUD for ``organizations``."""

from __future__ import annotations

from uuid import UUID

from src.catalog.base_repo import CatalogRepo
from src.catalog.models import Organization


class OrgRepository(CatalogRepo):
    async def list_all(self) -> list[Organization]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, created_at FROM organizations ORDER BY name"
            )
            return [Organization.model_validate(dict(r)) for r in rows]

    async def get(self, org_id: UUID) -> Organization | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, created_at FROM organizations WHERE id = $1",
                org_id,
            )
            return Organization.model_validate(dict(row)) if row else None

    async def get_by_name(self, name: str) -> Organization | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, created_at FROM organizations WHERE name = $1",
                name,
            )
            return Organization.model_validate(dict(row)) if row else None

    async def insert(self, name: str) -> Organization:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO organizations (name)
                VALUES ($1)
                RETURNING id, name, created_at
                """,
                name,
            )
            return Organization.model_validate(dict(row))

    async def update(self, org_id: UUID, *, name: str | None = None) -> Organization | None:
        if name is None:
            return await self.get(org_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE organizations SET name = $2
                WHERE id = $1
                RETURNING id, name, created_at
                """,
                org_id,
                name,
            )
            return Organization.model_validate(dict(row)) if row else None

    async def delete(self, org_id: UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM organizations WHERE id = $1",
                org_id,
            )
            return result.endswith(" 1")

    async def count(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM organizations") or 0

    async def ensure_default(self, name: str = "Default Organization") -> Organization:
        """Create the default org if no orgs exist.

        Phase 1 runs single-tenant. The plan recommends keeping the org table
        explicit from day one, but bootstrapping a default row so the setup
        wizard has something to pivot off if the user jumps straight to
        creating a team.
        """
        existing = await self.count()
        if existing > 0:
            rows = await self.list_all()
            return rows[0]
        return await self.insert(name)
