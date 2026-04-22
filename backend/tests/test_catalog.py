"""Catalog repository smoke tests.

These tests hit a real PostgreSQL instance. They're auto-skipped unless
``PRISM_POSTGRES_URL`` is set (typically pointing at the dockerized dev db
launched by ``run.sh``). On skip they still import cleanly so ``pytest
backend/tests`` won't fail on a box without a DB.

Each test runs on a fresh schema by pointing at a temporary database, then
drops it at teardown. The catalog module's schema bootstrap is the subject
under test, so we don't want to rely on state from prior runs.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from src.catalog import (
    OrgRepository,
    ServiceRepository,
    SourceRepository,
    TeamRepository,
)
from src.catalog.models import SourceCreate, SourceKind, SourceScope

PG_URL = os.environ.get("PRISM_TEST_POSTGRES_URL") or os.environ.get("PRISM_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    PG_URL is None,
    reason="Set PRISM_POSTGRES_URL or PRISM_TEST_POSTGRES_URL to exercise catalog tests",
)


async def _make_throwaway_db() -> tuple[str, str]:
    """Create a fresh db on the admin PG_URL and return its DSN + name."""
    assert PG_URL is not None
    admin = await asyncpg.connect(PG_URL)
    db_name = f"prism_test_{uuid.uuid4().hex[:10]}"
    try:
        await admin.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin.close()

    # Swap db name in the connection URL.
    # naive replacement -- good enough for local dev DSNs.
    dsn = PG_URL.rsplit("/", 1)[0] + f"/{db_name}"
    return dsn, db_name


async def _drop_throwaway_db(db_name: str) -> None:
    assert PG_URL is not None
    admin = await asyncpg.connect(PG_URL)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture
def fresh_dsn():
    async def _setup() -> tuple[str, str]:
        return await _make_throwaway_db()

    dsn, db_name = asyncio.run(_setup())
    yield dsn
    asyncio.run(_drop_throwaway_db(db_name))


def test_catalog_bootstrap_creates_tables(fresh_dsn: str):
    async def _run() -> None:
        repo = await OrgRepository.create(dsn=fresh_dsn)
        try:
            conn = await asyncpg.connect(fresh_dsn)
            try:
                names = [
                    row["table_name"]
                    for row in await conn.fetch(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public'
                        """
                    )
                ]
                for expected in (
                    "organizations",
                    "teams",
                    "services",
                    "sources",
                    "source_secrets",
                    "kg_documents",
                    "kg_dependencies",
                    "kg_pending_dependencies",
                    "document_registry",
                ):
                    assert expected in names, f"missing table: {expected}"
                # Legacy tables must not exist.
                for legacy in ("kg_teams", "kg_ownership", "kg_service_tech"):
                    assert legacy not in names, f"legacy table not dropped: {legacy}"
            finally:
                await conn.close()
        finally:
            await repo.close()

    asyncio.run(_run())


def test_crud_roundtrip_org_team_service(fresh_dsn: str):
    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform", "owns the platform")
            service = await services.insert(team.id, "auth-service", "https://gitlab.com/acme/auth")

            assert (await teams.list_for_org(org.id))[0].name == "Platform"
            assert (await services.list_for_team(team.id))[0].name == "auth-service"

            # Per-team uniqueness: same name in another team should succeed.
            team_b = await teams.insert(org.id, "Payments")
            await services.insert(team_b.id, "auth-service")

            # Updating: partial updates shouldn't wipe description.
            updated = await services.update(service.id, repo_url="https://example.com/new")
            assert updated is not None
            assert updated.repo_url == "https://example.com/new"
            assert updated.name == "auth-service"

            # find_any_by_name returns the first match across teams.
            match = await services.find_any_by_name("auth-service")
            assert match is not None
        finally:
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_source_create_enforces_one_scope(fresh_dsn: str):
    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        sources = await SourceRepository.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")

            src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.TEAM,
                    scope_id=team.id,
                    kind=SourceKind.GITLAB,
                    name="platform docs",
                    config={"group_path": "platform"},
                    token="glpat-test",
                )
            )

            assert src.team_id == team.id
            assert src.org_id is None
            assert src.service_id is None

            with_secret = await sources.get_with_secret(src.id)
            assert with_secret is not None and with_secret.token == "glpat-test"

            # Listing by scope filters correctly.
            by_org = await sources.list_sources(org_id=org.id)
            assert by_org == []
            by_team = await sources.list_sources(team_id=team.id)
            assert len(by_team) == 1
        finally:
            await sources.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_pending_dependencies_reconcile(fresh_dsn: str):
    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")
            from_service = await services.insert(team.id, "api-gateway")

            # Park an edge whose target doesn't exist yet.
            await services.add_pending_dependency(
                from_service.id,
                "auth-service",
                source_doc="gitlab/platform/api-gateway/README.md",
            )

            # Declare the missing service; reconciliation should move the edge.
            to_service = await services.insert(team.id, "auth-service")
            reconciled = await services.reconcile_pending_dependencies(to_service.id, "auth-service")
            assert reconciled == 1

            deps = await services.query_dependencies(from_service.id)
            assert any(d["to_service"] == "auth-service" for d in deps)
        finally:
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())
