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


def test_manual_dependency_add_remove(fresh_dsn: str):
    """User-managed deps replace the old auto-extraction + pending flow.

    Edges are written by the service detail page through ``add_dependency``
    and removed via ``remove_dependency``. ``query_dependencies`` walks
    the graph for downstream consumers (the dependency agent, blast
    radius, etc.).
    """
    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")
            from_service = await services.insert(team.id, "api-gateway")
            to_service = await services.insert(team.id, "auth-service")

            await services.add_dependency(
                from_service.id, to_service.id, source_doc="manual"
            )

            outbound = await services.list_outbound_dependencies(from_service.id)
            assert len(outbound) == 1
            assert outbound[0]["to_service_name"] == "auth-service"
            assert outbound[0]["source"] == "manual"

            removed = await services.remove_dependency(from_service.id, to_service.id)
            assert removed is True
            outbound_after = await services.list_outbound_dependencies(from_service.id)
            assert outbound_after == []

            # Removing a non-existent edge returns False rather than raising.
            removed_again = await services.remove_dependency(from_service.id, to_service.id)
            assert removed_again is False
        finally:
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_descendant_source_enumeration_for_org_and_team_deletes(fresh_dsn: str):
    """Catalog deletes need to enumerate descendant sources before the
    Postgres ``ON DELETE CASCADE`` runs -- after the cascade we have no
    handle left to drive OpenSearch cleanup, leaving chunks indexed
    under stale ``source_id``/``org_id``/``team_id``/``service_id``
    metadata.

    This test exercises the SQL behind the enumeration: ``org``-level
    enumeration walks org-direct + team-direct + service-attached
    sources; ``team``-level walks team-direct + service-attached.
    """
    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        sources = await SourceRepository.create(dsn=fresh_dsn)
        try:
            org_a = await orgs.insert("OrgA")
            org_b = await orgs.insert("OrgB")
            team_a1 = await teams.insert(org_a.id, "team-a1")
            team_a2 = await teams.insert(org_a.id, "team-a2")
            team_b1 = await teams.insert(org_b.id, "team-b1")
            svc_a1 = await services.insert(team_a1.id, "svc-a1")
            svc_a2 = await services.insert(team_a2.id, "svc-a2")
            svc_b1 = await services.insert(team_b1.id, "svc-b1")

            # Sprinkle sources at each scope axis. The enumeration
            # should pick the right slice for each delete kind.
            org_a_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.ORG, scope_id=org_a.id,
                    kind=SourceKind.GITLAB, name="org-A-src",
                    config={"project_path": "x/a"},
                )
            )
            team_a1_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.TEAM, scope_id=team_a1.id,
                    kind=SourceKind.GITLAB, name="team-A1-src",
                    config={"project_path": "x/b"},
                )
            )
            svc_a1_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE, scope_id=svc_a1.id,
                    kind=SourceKind.GITLAB, name="svc-A1-src",
                    config={"project_path": "x/c"},
                )
            )
            svc_a2_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE, scope_id=svc_a2.id,
                    kind=SourceKind.GITLAB, name="svc-A2-src",
                    config={"project_path": "x/d"},
                )
            )
            org_b_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.ORG, scope_id=org_b.id,
                    kind=SourceKind.GITLAB, name="org-B-src",
                    config={"project_path": "x/e"},
                )
            )
            svc_b1_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE, scope_id=svc_b1.id,
                    kind=SourceKind.GITLAB, name="svc-B1-src",
                    config={"project_path": "x/f"},
                )
            )

            # Org-A enumeration: every source touching org-A's tree.
            org_a_descendants = set(
                await sources.list_descendant_source_ids_for_org(org_a.id)
            )
            assert org_a_descendants == {
                org_a_src.id, team_a1_src.id, svc_a1_src.id, svc_a2_src.id
            }
            # Org B is untouched.
            assert org_b_src.id not in org_a_descendants
            assert svc_b1_src.id not in org_a_descendants

            # Team-A1 enumeration: just team_a1's direct + nested
            # service sources.
            team_a1_descendants = set(
                await sources.list_descendant_source_ids_for_team(team_a1.id)
            )
            assert team_a1_descendants == {team_a1_src.id, svc_a1_src.id}
            # team-A2's service source is NOT under team-A1.
            assert svc_a2_src.id not in team_a1_descendants
        finally:
            await sources.close()
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_external_dependency_crud_and_case_insensitive_dedup(fresh_dsn: str):
    """External deps round-trip through the repo, mix with catalog deps in
    listings, and dedupe case-insensitively.

    Case-insensitive uniqueness is enforced by the function-based unique
    index ``kg_dependencies_external_name_lower_uniq``. The UI dedupes
    by ``lower(name)`` too -- without DB enforcement two clients could
    race-create ``Stripe`` and ``stripe`` as separate edges.
    """
    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")
            from_svc = await services.insert(team.id, "auth-service")
            other_svc = await services.insert(team.id, "invoice-service")

            # Mix: one catalog dep, two externals (same name diff case).
            await services.add_dependency(from_svc.id, other_svc.id, source_doc="manual")
            await services.add_external_dependency(
                from_svc.id, "Stripe API", "Payment intents", source_doc="manual"
            )
            # Case-insensitive collision -- updates the description in place,
            # does not create a second row.
            await services.add_external_dependency(
                from_svc.id, "stripe api", "Payment intents v2", source_doc="manual"
            )

            outbound = await services.list_outbound_dependencies(from_svc.id)
            assert len(outbound) == 2

            externals = [d for d in outbound if d["kind"] == "external"]
            internals = [d for d in outbound if d["kind"] == "service"]
            assert len(externals) == 1
            assert len(internals) == 1
            # Description was updated by the second insert.
            assert externals[0]["description"] == "Payment intents v2"
            # Internal edge has no description but does carry the team name.
            assert internals[0]["to_service_name"] == "invoice-service"
            assert internals[0]["team_name"] == "Platform"

            # Removing by mismatched case still hits the row.
            removed = await services.remove_external_dependency(from_svc.id, "STRIPE API")
            assert removed is True
            after = await services.list_outbound_dependencies(from_svc.id)
            assert all(d["kind"] != "external" for d in after)

            # Idempotent removal returns False rather than raising.
            removed_again = await services.remove_external_dependency(from_svc.id, "stripe api")
            assert removed_again is False

            # External edges are excluded from the org-wide dependency listing
            # because the org graph only renders declared catalog nodes.
            await services.add_external_dependency(from_svc.id, "Auth0", "OIDC")
            graph_edges = await services.list_all_dependencies()
            assert all(e.get("to_service_id") for e in graph_edges)
            assert all("Auth0" not in (e.get("to_service") or "") for e in graph_edges)
        finally:
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_registry_composite_uniqueness_and_delete_by_paths(fresh_dsn: str):
    """Two sources can each have their own ``README.md`` (composite UNIQUE),
    and ``delete_by_paths`` only tombstones rows for the source it was
    given -- the other source's ``README.md`` is untouched.
    """
    from src.ingestion.registry import DocumentRegistry, compute_content_hash

    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        sources = await SourceRepository.create(dsn=fresh_dsn)
        registry = await DocumentRegistry.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")
            svc_a = await services.insert(team.id, "service-a")
            svc_b = await services.insert(team.id, "service-b")

            src_a = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE,
                    scope_id=svc_a.id,
                    kind=SourceKind.GITLAB,
                    name="A",
                    config={"project_path": "org/a"},
                )
            )
            src_b = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE,
                    scope_id=svc_b.id,
                    kind=SourceKind.GITLAB,
                    name="B",
                    config={"project_path": "org/b"},
                )
            )

            # Two sources, both with ``README.md`` -- the old global UNIQUE
            # constraint would have blown up here. The composite key
            # ``(source_id, source_path)`` lets both rows coexist.
            doc_a = str(uuid.uuid4())
            doc_b = str(uuid.uuid4())
            await registry.upsert(
                document_id=doc_a,
                source_platform="gitlab",
                source_path="README.md",
                content_hash=compute_content_hash("a"),
                chunk_count=2,
                source_id=src_a.id,
            )
            await registry.upsert(
                document_id=doc_b,
                source_platform="gitlab",
                source_path="README.md",
                content_hash=compute_content_hash("b"),
                chunk_count=3,
                source_id=src_b.id,
            )

            # ``delete_by_paths`` is per-source. Removing ``README.md`` for
            # source A must leave source B's row alone.
            removed = await registry.delete_by_paths(
                src_a.id, ["README.md", "missing.md"]
            )
            assert removed == [doc_a]

            still_a = await registry.get_by_path("README.md", source_id=src_a.id)
            still_b = await registry.get_by_path("README.md", source_id=src_b.id)
            assert still_a is None
            assert still_b is not None
            assert still_b["document_id"] == doc_b

            # ``delete_by_document_ids`` is the round-13 helper used by
            # the tombstone path: drops rows by document_id, scoped to
            # ``source_id`` so a stray doc_id from a different source
            # can't accidentally clobber rows it doesn't own.
            doc_b2 = str(uuid.uuid4())
            await registry.upsert(
                document_id=doc_b2,
                source_platform="gitlab",
                source_path="OTHER.md",
                content_hash=compute_content_hash("b2"),
                chunk_count=1,
                source_id=src_b.id,
            )
            # Pass src_a.id with a doc_id that lives under src_b -- it
            # must NOT be deleted because the predicate is ``source_id
            # AND document_id``.
            removed_cross = await registry.delete_by_document_ids(
                src_a.id, [doc_b2]
            )
            assert removed_cross == []
            assert (
                await registry.get_by_path("OTHER.md", source_id=src_b.id)
            ) is not None

            # Right-source delete works.
            removed_correct = await registry.delete_by_document_ids(
                src_b.id, [doc_b2]
            )
            assert removed_correct == [doc_b2]
        finally:
            await registry.close()
            await sources.close()
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_tombstone_drops_both_registry_and_kg_documents(fresh_dsn: str):
    """Tombstone-helper drops ``document_registry`` AND ``kg_documents``
    rows for the supplied ``document_id``s in a single transaction.

    The pipeline only passes doc_ids whose OpenSearch chunks were
    confirmed gone, so withholding an id (simulating a failed OS
    cleanup) must leave BOTH rows in place for the next ingest to
    retry. Without that retention the registry would lose the document
    handle and orphan chunks would remain searchable forever.
    """
    from src.ingestion.knowledge_store import KnowledgeStore
    from src.ingestion.registry import DocumentRegistry, compute_content_hash
    from src.models.document import DocumentMetadata, DocumentRef, RawDocument

    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        sources = await SourceRepository.create(dsn=fresh_dsn)
        registry = await DocumentRegistry.create(dsn=fresh_dsn)
        store = await KnowledgeStore.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")
            svc = await services.insert(team.id, "service-a")
            src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE,
                    scope_id=svc.id,
                    kind=SourceKind.GITLAB,
                    name="A",
                    config={"project_path": "org/a"},
                )
            )

            doc_keep = str(uuid.uuid4())
            doc_drop = str(uuid.uuid4())

            # Two ingested documents, both rows in registry + kg_documents.
            for doc_id, path in [(doc_keep, "keep.md"), (doc_drop, "drop.md")]:
                await registry.upsert(
                    document_id=doc_id,
                    source_platform="gitlab",
                    source_path=path,
                    content_hash=compute_content_hash(path),
                    chunk_count=1,
                    source_id=src.id,
                )
                await store.add_document(
                    doc_id,
                    RawDocument(
                        ref=DocumentRef(
                            source_platform="gitlab",
                            source_path=path,
                        ),
                        content="x",
                        metadata=DocumentMetadata(title=path),
                    ),
                    source_id=src.id,
                    org_id=org.id,
                    team_id=team.id,
                    service_id=svc.id,
                )

            # Pipeline contract: only pass doc_ids whose OS chunks are
            # confirmed gone. Here ``doc_keep`` simulates a failed OS
            # cleanup (caller withholds it) and ``doc_drop`` is the
            # success case.
            removed = await registry.delete_by_document_ids_with_graph(
                src.id, [doc_drop]
            )
            assert removed == [doc_drop]

            async with registry.pool.acquire() as conn:
                # ``doc_drop`` is gone from BOTH tables.
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM document_registry WHERE document_id = $1",
                        doc_drop,
                    )
                    is None
                )
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM kg_documents WHERE id = $1",
                        doc_drop,
                    )
                    is None
                )
                # ``doc_keep`` retained in BOTH tables -- next ingest
                # will retry the OpenSearch cleanup with the same
                # document_id.
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM document_registry WHERE document_id = $1",
                        doc_keep,
                    )
                    is not None
                )
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM kg_documents WHERE id = $1",
                        doc_keep,
                    )
                    is not None
                )

            # Defensive scope check: passing a stranger source's id with
            # the surviving doc_id is a no-op.
            other_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE,
                    scope_id=svc.id,
                    kind=SourceKind.GITLAB,
                    name="B",
                    config={"project_path": "org/b"},
                )
            )
            no_op = await registry.delete_by_document_ids_with_graph(
                other_src.id, [doc_keep]
            )
            assert no_op == []
            async with registry.pool.acquire() as conn:
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM kg_documents WHERE id = $1",
                        doc_keep,
                    )
                    is not None
                )
        finally:
            await store.close()
            await registry.close()
            await sources.close()
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())


def test_content_update_leaves_exactly_one_row_per_table(fresh_dsn: str):
    """Re-ingesting the same ``source_path`` with changed content must
    leave exactly one ``document_registry`` row AND one ``kg_documents``
    row for the (source_id, source_path) pair.

    The pipeline's content-update path generates a fresh ``document_id``
    for the new chunk set. ``registry.upsert`` re-points
    ``document_registry`` at the new id via ON CONFLICT(source_id,
    source_path), but the old ``kg_documents`` row stays orphaned
    because ON CONFLICT(id) on the new graph row can't reach the
    previous id. The pipeline drops the orphan via
    ``KnowledgeStore.delete_documents`` after the new graph row +
    registry upsert have committed; this test exercises that sequence
    directly.
    """
    from src.ingestion.knowledge_store import KnowledgeStore
    from src.ingestion.registry import DocumentRegistry, compute_content_hash
    from src.models.document import DocumentMetadata, DocumentRef, RawDocument

    async def _run() -> None:
        orgs = await OrgRepository.create(dsn=fresh_dsn)
        teams = await TeamRepository.create(dsn=fresh_dsn)
        services = await ServiceRepository.create(dsn=fresh_dsn)
        sources = await SourceRepository.create(dsn=fresh_dsn)
        registry = await DocumentRegistry.create(dsn=fresh_dsn)
        store = await KnowledgeStore.create(dsn=fresh_dsn)
        try:
            org = await orgs.insert("Acme")
            team = await teams.insert(org.id, "Platform")
            svc = await services.insert(team.id, "service-a")
            src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE,
                    scope_id=svc.id,
                    kind=SourceKind.GITLAB,
                    name="A",
                    config={"project_path": "org/a"},
                )
            )

            path = "README.md"
            old_doc_id = str(uuid.uuid4())
            new_doc_id = str(uuid.uuid4())

            def _doc(doc_id: str) -> RawDocument:
                return RawDocument(
                    ref=DocumentRef(
                        source_platform="gitlab",
                        source_path=path,
                    ),
                    content="x",
                    metadata=DocumentMetadata(title=path),
                )

            # First ingest: registry + kg_documents both pointing to old id.
            await store.add_document(
                old_doc_id,
                _doc(old_doc_id),
                source_id=src.id,
                org_id=org.id,
                team_id=team.id,
                service_id=svc.id,
            )
            await registry.upsert(
                document_id=old_doc_id,
                source_platform="gitlab",
                source_path=path,
                content_hash=compute_content_hash("v1"),
                chunk_count=2,
                source_id=src.id,
            )

            # Content-update sequence as the pipeline runs it: new graph
            # row, registry upsert (re-points document_id), then drop the
            # orphaned old kg_documents row.
            await store.add_document(
                new_doc_id,
                _doc(new_doc_id),
                source_id=src.id,
                org_id=org.id,
                team_id=team.id,
                service_id=svc.id,
            )
            await registry.upsert(
                document_id=new_doc_id,
                source_platform="gitlab",
                source_path=path,
                content_hash=compute_content_hash("v2"),
                chunk_count=3,
                source_id=src.id,
            )
            dropped = await store.delete_documents(src.id, [old_doc_id])
            assert dropped == 1

            async with registry.pool.acquire() as conn:
                # Exactly one registry row for the (source, path) pair,
                # pointing at the new doc id.
                reg_rows = await conn.fetch(
                    """
                    SELECT document_id FROM document_registry
                    WHERE source_id = $1 AND source_path = $2
                    """,
                    src.id,
                    path,
                )
                assert len(reg_rows) == 1
                assert reg_rows[0]["document_id"] == new_doc_id

                # Exactly one kg_documents row for the source's
                # (source_id, path) pair, also pointing at the new id.
                kg_rows = await conn.fetch(
                    "SELECT id FROM kg_documents WHERE source_id = $1 AND path = $2",
                    src.id,
                    path,
                )
                assert len(kg_rows) == 1
                assert kg_rows[0]["id"] == new_doc_id

                # Old graph row gone; new one present (defensive check).
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM kg_documents WHERE id = $1",
                        old_doc_id,
                    )
                    is None
                )
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM kg_documents WHERE id = $1",
                        new_doc_id,
                    )
                    is not None
                )

            # Cross-source defensive scope: deleting the new doc_id under
            # a stranger source must be a no-op.
            other_src = await sources.insert(
                SourceCreate(
                    scope=SourceScope.SERVICE,
                    scope_id=svc.id,
                    kind=SourceKind.GITLAB,
                    name="other",
                    config={"project_path": "org/other"},
                )
            )
            no_op = await store.delete_documents(other_src.id, [new_doc_id])
            assert no_op == 0
            async with registry.pool.acquire() as conn:
                assert (
                    await conn.fetchrow(
                        "SELECT 1 FROM kg_documents WHERE id = $1",
                        new_doc_id,
                    )
                    is not None
                )
        finally:
            await store.close()
            await registry.close()
            await sources.close()
            await services.close()
            await teams.close()
            await orgs.close()

    asyncio.run(_run())
