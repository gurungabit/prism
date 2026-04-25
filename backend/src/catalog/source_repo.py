"""CRUD for ``sources`` + ``source_secrets`` + ingestion status transitions.

Sources drive the rest of the pipeline. Every ingested chunk carries the scope
that came from its source. Secrets live in a sibling table so the common
``list sources`` path never returns tokens, and so rotation is a single-row
update.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from src.catalog.base_repo import CatalogRepo
from src.catalog.models import (
    Source,
    SourceCreate,
    SourceKind,
    SourceScope,
    SourceStatus,
    SourceUpdate,
    SourceWithSecret,
)


def _row_to_source(row) -> Source:
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    return Source.model_validate(
        {
            "id": row["id"],
            "org_id": row["org_id"],
            "team_id": row["team_id"],
            "service_id": row["service_id"],
            "kind": row["kind"],
            "name": row["name"],
            "config": config or {},
            "secret_ref": row["secret_ref"],
            "status": row["status"],
            "last_ingested_at": row["last_ingested_at"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
        }
    )


class SourceRepository(CatalogRepo):
    async def insert(self, payload: SourceCreate) -> Source:
        # Map the (scope, scope_id) discriminator onto exactly one of the
        # nullable foreign keys. This mirrors the CHECK constraint.
        org_id = payload.scope_id if payload.scope == SourceScope.ORG else None
        team_id = payload.scope_id if payload.scope == SourceScope.TEAM else None
        service_id = payload.scope_id if payload.scope == SourceScope.SERVICE else None

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO sources (
                        org_id, team_id, service_id, kind, name, config,
                        secret_ref, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'pending')
                    RETURNING id, org_id, team_id, service_id, kind, name, config,
                              secret_ref, status, last_ingested_at, last_error, created_at
                    """,
                    org_id,
                    team_id,
                    service_id,
                    payload.kind.value,
                    payload.name,
                    json.dumps(payload.config),
                    None,
                )
                source = _row_to_source(row)

                if payload.token:
                    await conn.execute(
                        """
                        INSERT INTO source_secrets (source_id, token, updated_at)
                        VALUES ($1, $2, now())
                        ON CONFLICT (source_id) DO UPDATE SET
                            token = EXCLUDED.token,
                            updated_at = now()
                        """,
                        source.id,
                        payload.token,
                    )

                return source

    async def list_sources(
        self,
        *,
        org_id: UUID | None = None,
        team_id: UUID | None = None,
        service_id: UUID | None = None,
    ) -> list[Source]:
        # ``(None, None, None)`` returns every source across every scope.
        # Useful for the /sources landing page where the user has only the
        # default org and wants to see everything at a glance.
        clauses: list[str] = []
        args: list = []
        idx = 1
        if org_id is not None:
            clauses.append(f"org_id = ${idx}")
            args.append(org_id)
            idx += 1
        if team_id is not None:
            clauses.append(f"team_id = ${idx}")
            args.append(team_id)
            idx += 1
        if service_id is not None:
            clauses.append(f"service_id = ${idx}")
            args.append(service_id)
            idx += 1

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, org_id, team_id, service_id, kind, name, config,
                       secret_ref, status, last_ingested_at, last_error, created_at
                FROM sources
                {where}
                ORDER BY created_at DESC
                """,
                *args,
            )
            return [_row_to_source(r) for r in rows]

    async def get(self, source_id: UUID) -> Source | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, org_id, team_id, service_id, kind, name, config,
                       secret_ref, status, last_ingested_at, last_error, created_at
                FROM sources WHERE id = $1
                """,
                source_id,
            )
            return _row_to_source(row) if row else None

    async def get_with_secret(self, source_id: UUID) -> SourceWithSecret | None:
        async with self.pool.acquire() as conn:
            source_row = await conn.fetchrow(
                """
                SELECT id, org_id, team_id, service_id, kind, name, config,
                       secret_ref, status, last_ingested_at, last_error, created_at
                FROM sources WHERE id = $1
                """,
                source_id,
            )
            if source_row is None:
                return None

            secret_row = await conn.fetchrow(
                "SELECT token FROM source_secrets WHERE source_id = $1",
                source_id,
            )

            return SourceWithSecret(
                source=_row_to_source(source_row),
                token=secret_row["token"] if secret_row else None,
            )

    async def update(self, source_id: UUID, payload: SourceUpdate) -> Source | None:
        sets: list[str] = []
        args: list = []
        idx = 2
        if payload.name is not None:
            sets.append(f"name = ${idx}")
            args.append(payload.name)
            idx += 1
        if payload.config is not None:
            sets.append(f"config = ${idx}::jsonb")
            args.append(json.dumps(payload.config))
            idx += 1
        if payload.status is not None:
            sets.append(f"status = ${idx}")
            args.append(payload.status.value)
            idx += 1
        if payload.last_error is not None:
            sets.append(f"last_error = ${idx}")
            args.append(payload.last_error)
            idx += 1

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if sets:
                    row = await conn.fetchrow(
                        f"""
                        UPDATE sources SET {', '.join(sets)}
                        WHERE id = $1
                        RETURNING id, org_id, team_id, service_id, kind, name, config,
                                  secret_ref, status, last_ingested_at, last_error, created_at
                        """,
                        source_id,
                        *args,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        SELECT id, org_id, team_id, service_id, kind, name, config,
                               secret_ref, status, last_ingested_at, last_error, created_at
                        FROM sources WHERE id = $1
                        """,
                        source_id,
                    )

                if row is None:
                    return None

                if payload.token is not None:
                    if payload.token == "":
                        await conn.execute(
                            "DELETE FROM source_secrets WHERE source_id = $1",
                            source_id,
                        )
                    else:
                        await conn.execute(
                            """
                            INSERT INTO source_secrets (source_id, token, updated_at)
                            VALUES ($1, $2, now())
                            ON CONFLICT (source_id) DO UPDATE SET
                                token = EXCLUDED.token,
                                updated_at = now()
                            """,
                            source_id,
                            payload.token,
                        )

                return _row_to_source(row)

    async def delete(self, source_id: UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM sources WHERE id = $1",
                source_id,
            )
            return result.endswith(" 1")

    async def try_claim_for_sync(self, source_id: UUID) -> bool:
        """Atomic compare-and-set that flips a source to ``syncing`` only if
        it isn't already in flight. Returns True if this caller owns the
        sync, False if another run already does. Used by the ingest API
        endpoint to reject concurrent click-spam without enqueuing a second
        background task.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sources
                SET status = 'syncing',
                    last_error = NULL
                WHERE id = $1 AND status != 'syncing'
                """,
                source_id,
            )
            return result.endswith(" 1")

    async def mark_status(
        self,
        source_id: UUID,
        status: SourceStatus,
        *,
        last_error: str | None = None,
        last_ingested_at: datetime | None = None,
    ) -> None:
        # The pipeline calls this at each transition: pending -> syncing ->
        # ready | error. ``last_ingested_at`` only gets set on ready, so a
        # failed run still shows the previous successful timestamp.
        async with self.pool.acquire() as conn:
            if last_ingested_at is not None:
                await conn.execute(
                    """
                    UPDATE sources
                    SET status = $2,
                        last_error = $3,
                        last_ingested_at = $4
                    WHERE id = $1
                    """,
                    source_id,
                    status.value,
                    last_error,
                    last_ingested_at,
                )
            else:
                await conn.execute(
                    """
                    UPDATE sources
                    SET status = $2,
                        last_error = $3
                    WHERE id = $1
                    """,
                    source_id,
                    status.value,
                    last_error,
                )

    async def reset_orphaned_syncing(self) -> int:
        # Any row still marked ``syncing`` at process startup is orphaned:
        # the background task that owned the state didn't survive the restart,
        # so the status will never transition on its own. Flip these back to
        # ``error`` with a note so the UI unlocks the Sync button.
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sources
                SET status = 'error',
                    last_error = 'Ingest interrupted by restart'
                WHERE status = 'syncing'
                """,
            )
            # asyncpg returns "UPDATE N"
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0

    async def count_docs(self, source_id: UUID) -> int:
        """Count declared source's indexed docs (for the sources list UI)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM kg_documents WHERE source_id = $1",
                source_id,
            ) or 0

    async def list_documents(self, source_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT dr.document_id, dr.source_path, dr.chunk_count, dr.status,
                       dr.last_ingested_at, dr.source_platform,
                       kd.title, kd.source_url
                FROM document_registry dr
                LEFT JOIN kg_documents kd ON kd.id = dr.document_id
                WHERE dr.source_id = $1
                ORDER BY dr.last_ingested_at DESC NULLS LAST
                """,
                source_id,
            )
            return [dict(r) for r in rows]
