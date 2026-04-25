"""FastAPI routes for the declared catalog + ingestion triggers.

These are the CRUD endpoints the setup wizard uses: create the org, add
teams, add services, attach sources, kick off ingestion. They replace the
legacy ``/api/ingest`` + ``/api/graph/teams`` surface.

Every route opens its own repository instance. The repositories share the
global connection pool, so this is cheap (no new pool per request); it keeps
each handler self-contained without a FastAPI dependency tree.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.catalog import (
    OrgRepository,
    ServiceRepository,
    SourceRepository,
    TeamRepository,
)
from src.catalog.models import (
    Organization,
    Service,
    Source,
    SourceCreate,
    SourceKind,
    SourceScope,
    SourceStatus,
    SourceUpdate,
    Team,
)
from src.connectors.base import SourceConfig
from src.connectors.gitlab import GitLabAPIError, GitLabConnector
from src.ingestion.indexer import delete_by_source_id, get_opensearch_client
from src.ingestion.pipeline import IngestionPipeline
from src.observability.logging import get_logger

log = get_logger("catalog_routes")

router = APIRouter(prefix="/api")


def _delete_opensearch_for_sources(
    source_ids: list[UUID],
    *,
    scope: str,
) -> None:
    """Best-effort + abort-on-failure OpenSearch cleanup for catalog deletes.

    The Postgres ``ON DELETE CASCADE`` chain handles every relational row
    (teams, services, sources, ``source_secrets``, ``kg_documents``,
    ``document_registry``, ``kg_dependencies``) when an org / team /
    service is dropped. OpenSearch is a separate store: chunks are keyed
    by ``source_id`` and won't be touched by the cascade. This helper
    walks the soon-to-be-deleted source ids and runs
    ``delete_by_source_id`` for each *before* the Postgres delete runs --
    after the cascade we'd have no handle left to drive a retry.

    Cleanup failure aborts the whole catalog delete with 503 so we don't
    leave the deployment in the worst-of-both state where the catalog
    row is gone but its chunks still match retrieval queries with stale
    org/team/service metadata. The caller decides whether to retry once
    OpenSearch is healthy again.

    No-op when the list is empty -- common for a brand-new catalog node
    that hasn't had a source attached yet.
    """
    if not source_ids:
        return
    client = get_opensearch_client()
    failures: list[str] = []
    for sid in source_ids:
        try:
            delete_by_source_id(sid, client)
        except Exception as e:  # noqa: BLE001
            log.error(
                "catalog_delete_opensearch_cleanup_failed",
                scope=scope,
                source_id=str(sid),
                error=str(e)[:300],
            )
            failures.append(str(sid))
    if failures:
        raise HTTPException(
            status_code=503,
            detail=(
                f"OpenSearch cleanup failed for {len(failures)} of "
                f"{len(source_ids)} descendant source(s); aborting "
                f"catalog delete to avoid orphaned chunks. Retry once "
                f"OpenSearch is healthy."
            ),
        )


# ---------- request/response models ----------


class OrgCreateBody(BaseModel):
    name: str


class OrgUpdateBody(BaseModel):
    name: str | None = None


class TeamCreateBody(BaseModel):
    name: str
    description: str = ""


class TeamUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None


class ServiceCreateBody(BaseModel):
    name: str
    repo_url: str = ""
    description: str = ""


class ServiceUpdateBody(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    description: str | None = None


class SourceCreateBody(BaseModel):
    scope: SourceScope
    scope_id: UUID
    kind: SourceKind
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None


class SourceUpdateBody(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    token: str | None = None


class SourceValidateBody(BaseModel):
    """Inputs for the "test connection" action in the source wizard."""

    kind: SourceKind
    config: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None


class GitLabProjectSearchBody(BaseModel):
    """Inputs for the GitLab project-picker dropdown in the source wizard."""

    base_url: str | None = None
    token: str | None = None
    q: str = ""
    page: int = 1
    per_page: int = 20


class GitLabGroupSearchBody(BaseModel):
    """Inputs for the GitLab group-picker dropdown (whole-group ingest mode)."""

    base_url: str | None = None
    token: str | None = None
    q: str = ""
    page: int = 1
    per_page: int = 20


# ---------- orgs ----------


@router.post("/orgs")
async def create_org(body: OrgCreateBody) -> Organization:
    repo = await OrgRepository.create()
    try:
        existing = await repo.get_by_name(body.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Organization '{body.name}' already exists")
        return await repo.insert(body.name)
    finally:
        await repo.close()


@router.get("/orgs")
async def list_orgs() -> dict[str, list[Organization]]:
    repo = await OrgRepository.create()
    try:
        return {"orgs": await repo.list_all()}
    finally:
        await repo.close()


@router.get("/orgs/{org_id}")
async def get_org(org_id: UUID) -> Organization:
    repo = await OrgRepository.create()
    try:
        org = await repo.get(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org
    finally:
        await repo.close()


@router.patch("/orgs/{org_id}")
async def update_org(org_id: UUID, body: OrgUpdateBody) -> Organization:
    repo = await OrgRepository.create()
    try:
        updated = await repo.update(org_id, name=body.name)
        if updated is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return updated
    finally:
        await repo.close()


@router.delete("/orgs/{org_id}")
async def delete_org(org_id: UUID) -> dict[str, str]:
    org_repo = await OrgRepository.create()
    source_repo = await SourceRepository.create()
    try:
        # Postgres ON DELETE CASCADE handles teams/services/sources/registry,
        # but OpenSearch is a separate store -- chunks indexed under any of
        # this org's descendant sources would orphan. Enumerate first, clean
        # OS, only then drop the Postgres handle. Cleanup failure aborts
        # the whole delete so we don't leave the catalog in a state where
        # the only handle on the chunks is gone.
        descendant_ids = await source_repo.list_descendant_source_ids_for_org(org_id)
        _delete_opensearch_for_sources(descendant_ids, scope=f"org={org_id}")

        deleted = await org_repo.delete(org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Organization not found")
        return {"status": "deleted", "org_id": str(org_id)}
    finally:
        await source_repo.close()
        await org_repo.close()


# ---------- teams ----------


@router.post("/orgs/{org_id}/teams")
async def create_team(org_id: UUID, body: TeamCreateBody) -> Team:
    org_repo = await OrgRepository.create()
    team_repo = await TeamRepository.create()
    try:
        org = await org_repo.get(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")

        existing = await team_repo.get_by_name(org_id, body.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Team '{body.name}' already exists in this org")

        return await team_repo.insert(org_id, body.name, body.description)
    finally:
        await team_repo.close()
        await org_repo.close()


@router.get("/orgs/{org_id}/teams")
async def list_teams_for_org(org_id: UUID) -> dict[str, list[Team]]:
    repo = await TeamRepository.create()
    try:
        return {"teams": await repo.list_for_org(org_id)}
    finally:
        await repo.close()


@router.get("/teams/{team_id}")
async def get_team(team_id: UUID) -> Team:
    repo = await TeamRepository.create()
    try:
        team = await repo.get(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        return team
    finally:
        await repo.close()


@router.patch("/teams/{team_id}")
async def update_team(team_id: UUID, body: TeamUpdateBody) -> Team:
    repo = await TeamRepository.create()
    try:
        updated = await repo.update(team_id, name=body.name, description=body.description)
        if updated is None:
            raise HTTPException(status_code=404, detail="Team not found")
        return updated
    finally:
        await repo.close()


@router.delete("/teams/{team_id}")
async def delete_team(team_id: UUID) -> dict[str, str]:
    team_repo = await TeamRepository.create()
    source_repo = await SourceRepository.create()
    try:
        # See ``delete_org`` for the rationale -- enumerate descendant
        # sources, clean their OpenSearch chunks, only then cascade.
        descendant_ids = await source_repo.list_descendant_source_ids_for_team(team_id)
        _delete_opensearch_for_sources(descendant_ids, scope=f"team={team_id}")

        deleted = await team_repo.delete(team_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Team not found")
        return {"status": "deleted", "team_id": str(team_id)}
    finally:
        await source_repo.close()
        await team_repo.close()


# ---------- services ----------


@router.post("/teams/{team_id}/services")
async def create_service(team_id: UUID, body: ServiceCreateBody) -> Service:
    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    try:
        team = await team_repo.get(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")

        existing = await service_repo.get_by_name(team_id, body.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Service '{body.name}' already exists in team '{team.name}'",
            )

        service = await service_repo.insert(team_id, body.name, body.repo_url, body.description)
        return service
    finally:
        await service_repo.close()
        await team_repo.close()


@router.get("/teams/{team_id}/services")
async def list_services_for_team(team_id: UUID) -> dict[str, list[Service]]:
    repo = await ServiceRepository.create()
    try:
        return {"services": await repo.list_for_team(team_id)}
    finally:
        await repo.close()


@router.get("/services/{service_id}")
async def get_service(service_id: UUID) -> Service:
    repo = await ServiceRepository.create()
    try:
        service = await repo.get(service_id)
        if service is None:
            raise HTTPException(status_code=404, detail="Service not found")
        return service
    finally:
        await repo.close()


@router.patch("/services/{service_id}")
async def update_service(service_id: UUID, body: ServiceUpdateBody) -> Service:
    repo = await ServiceRepository.create()
    try:
        updated = await repo.update(
            service_id,
            name=body.name,
            repo_url=body.repo_url,
            description=body.description,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Service not found")
        return updated
    finally:
        await repo.close()


@router.delete("/services/{service_id}")
async def delete_service(service_id: UUID) -> dict[str, str]:
    service_repo = await ServiceRepository.create()
    source_repo = await SourceRepository.create()
    try:
        # Enumerate sources directly attached to this service; cascade
        # delete will tear them away with no chance to clean OS.
        descendant_sources = await source_repo.list_sources(service_id=service_id)
        descendant_ids = [s.id for s in descendant_sources]
        _delete_opensearch_for_sources(descendant_ids, scope=f"service={service_id}")

        deleted = await service_repo.delete(service_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Service not found")
        return {"status": "deleted", "service_id": str(service_id)}
    finally:
        await source_repo.close()
        await service_repo.close()


# ---------- service dependencies (manual) ----------


class ServiceDependencyCreateBody(BaseModel):
    """Add an internal (catalog) or external dependency edge.

    Exactly one of ``to_service_id`` or ``to_external_name`` must be set:
    the first wires the edge to a declared catalog service; the second
    records a free-text target outside the catalog (Stripe, Auth0, an
    upstream team's API, etc.) along with an optional description.

    Length caps prevent multi-MB payloads from sneaking into the DB and
    keep the UI's display layout sane. They're generous on purpose.
    """

    to_service_id: UUID | None = None
    to_external_name: str | None = Field(default=None, max_length=200)
    to_external_description: str = Field(default="", max_length=2000)


@router.get("/services/{service_id}/dependencies")
async def list_service_dependencies(service_id: UUID) -> dict[str, list[dict[str, Any]]]:
    """Outbound deps for a single service -- what this service depends on."""
    repo = await ServiceRepository.create()
    try:
        service = await repo.get(service_id)
        if service is None:
            raise HTTPException(status_code=404, detail="Service not found")
        return {"dependencies": await repo.list_outbound_dependencies(service_id)}
    finally:
        await repo.close()


@router.post("/services/{service_id}/dependencies")
async def add_service_dependency(
    service_id: UUID,
    body: ServiceDependencyCreateBody,
) -> dict[str, str]:
    has_internal = body.to_service_id is not None
    has_external = bool(body.to_external_name and body.to_external_name.strip())
    if has_internal == has_external:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of to_service_id or to_external_name",
        )
    repo = await ServiceRepository.create()
    try:
        src = await repo.get(service_id)
        if src is None:
            raise HTTPException(status_code=404, detail="Source service not found")

        if has_internal:
            assert body.to_service_id is not None  # narrow for type-checkers
            if service_id == body.to_service_id:
                raise HTTPException(
                    status_code=400, detail="A service cannot depend on itself"
                )
            dst = await repo.get(body.to_service_id)
            if dst is None:
                raise HTTPException(status_code=404, detail="Target service not found")
            # ``source='manual'`` marks the edge as user-entered so we can
            # visually distinguish hand-drawn edges from any future
            # automated source.
            await repo.add_dependency(
                service_id, body.to_service_id, source_doc="manual"
            )
        else:
            assert body.to_external_name is not None
            await repo.add_external_dependency(
                service_id,
                body.to_external_name.strip(),
                body.to_external_description.strip(),
                source_doc="manual",
            )
        return {"status": "added"}
    finally:
        await repo.close()


# NOTE: The external-delete route MUST be registered before the
# UUID-typed catalog-delete route. FastAPI matches in declaration order,
# and ``/dependencies/external`` would otherwise match the path-parameter
# variant first -- with ``to_service_id="external"`` -- and fail UUID
# parsing with a 422 before the more-specific route is even checked.
@router.delete("/services/{service_id}/dependencies/external")
async def delete_external_service_dependency(
    service_id: UUID,
    name: str,
) -> dict[str, str]:
    """Remove an external (free-text) dependency edge.

    The target name is passed as a query parameter -- not a path segment --
    so names containing ``/``, ``?``, ``#`` or pre-encoded ``%2F`` don't
    break route matching. Matching is case-insensitive to mirror the
    storage uniqueness.
    """
    repo = await ServiceRepository.create()
    try:
        removed = await repo.remove_external_dependency(service_id, name)
        if not removed:
            raise HTTPException(status_code=404, detail="Dependency not found")
        return {"status": "removed"}
    finally:
        await repo.close()


@router.delete("/services/{service_id}/dependencies/{to_service_id}")
async def delete_service_dependency(
    service_id: UUID,
    to_service_id: UUID,
) -> dict[str, str]:
    """Remove an internal (catalog) dependency edge."""
    repo = await ServiceRepository.create()
    try:
        removed = await repo.remove_dependency(service_id, to_service_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Dependency not found")
        return {"status": "removed"}
    finally:
        await repo.close()


# ---------- sources ----------


@router.post("/sources")
async def create_source(body: SourceCreateBody) -> Source:
    org_repo = await OrgRepository.create()
    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    source_repo = await SourceRepository.create()
    try:
        # Validate the scope target exists before inserting. Nice error
        # messages beat raw CHECK-constraint violations.
        if body.scope == SourceScope.ORG:
            if await org_repo.get(body.scope_id) is None:
                raise HTTPException(status_code=404, detail="Organization not found for source scope")
        elif body.scope == SourceScope.TEAM:
            if await team_repo.get(body.scope_id) is None:
                raise HTTPException(status_code=404, detail="Team not found for source scope")
        elif body.scope == SourceScope.SERVICE:
            if await service_repo.get(body.scope_id) is None:
                raise HTTPException(status_code=404, detail="Service not found for source scope")

        return await source_repo.insert(
            SourceCreate(
                scope=body.scope,
                scope_id=body.scope_id,
                kind=body.kind,
                name=body.name,
                config=body.config,
                token=body.token,
            )
        )
    finally:
        await source_repo.close()
        await service_repo.close()
        await team_repo.close()
        await org_repo.close()


@router.get("/sources")
async def list_sources(
    org_id: UUID | None = None,
    team_id: UUID | None = None,
    service_id: UUID | None = None,
) -> dict[str, Any]:
    source_repo = await SourceRepository.create()
    try:
        sources = await source_repo.list_sources(
            org_id=org_id, team_id=team_id, service_id=service_id
        )
        # Hydrate each source with its declared document count so the
        # /sources landing page can show "N documents" without a round-trip.
        enriched: list[dict] = []
        for source in sources:
            doc_count = await source_repo.count_docs(source.id)
            enriched.append(
                {
                    **source.model_dump(mode="json"),
                    "document_count": doc_count,
                }
            )
        return {"sources": enriched, "total": len(enriched)}
    finally:
        await source_repo.close()


@router.get("/sources/{source_id}")
async def get_source(source_id: UUID) -> dict[str, Any]:
    source_repo = await SourceRepository.create()
    try:
        source = await source_repo.get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")

        documents = await source_repo.list_documents(source_id)
        return {
            **source.model_dump(mode="json"),
            "documents": documents,
            "document_count": len(documents),
        }
    finally:
        await source_repo.close()


@router.get("/sources/{source_id}/status")
async def get_source_status(source_id: UUID) -> dict[str, Any]:
    source_repo = await SourceRepository.create()
    try:
        source = await source_repo.get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return {
            "source_id": str(source.id),
            "status": source.status,
            "last_ingested_at": source.last_ingested_at.isoformat() if source.last_ingested_at else None,
            "last_error": source.last_error,
        }
    finally:
        await source_repo.close()


@router.patch("/sources/{source_id}")
async def update_source(source_id: UUID, body: SourceUpdateBody) -> Source:
    source_repo = await SourceRepository.create()
    try:
        updated = await source_repo.update(
            source_id,
            SourceUpdate(
                name=body.name,
                config=body.config,
                token=body.token,
            ),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return updated
    finally:
        await source_repo.close()


@router.delete("/sources/{source_id}")
async def delete_source(source_id: UUID) -> dict[str, str]:
    source_repo = await SourceRepository.create()
    try:
        # Verify the source exists before touching OpenSearch -- a 404
        # is friendlier than spuriously running a delete-by-source query
        # against an index for a row that was never there.
        source = await source_repo.get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")

        # Same abort-pattern as org/team/service delete: clean OpenSearch
        # *first*, fail loudly if it doesn't work. Pre-fix, OS cleanup
        # failures were logged-and-ignored and the Postgres row was
        # dropped anyway -- after which the only handle on those chunks
        # was gone, leaving them indexed with stale source/org/team/
        # service metadata. Returning 503 keeps the source row intact
        # so the user (or a future durable-retry worker) can try again
        # once OpenSearch is healthy.
        _delete_opensearch_for_sources([source.id], scope=f"source={source_id}")

        deleted = await source_repo.delete(source_id)
        if not deleted:
            # The pre-check resolved the row, so a missing-on-delete
            # here means a concurrent delete won the race. Treat as
            # 404 for parity with the pre-check branch.
            raise HTTPException(status_code=404, detail="Source not found")
        return {"status": "deleted", "source_id": str(source_id)}
    finally:
        await source_repo.close()


@router.post("/sources/{source_id}/ingest")
async def trigger_source_ingest(
    source_id: UUID,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict[str, Any]:
    source_repo = await SourceRepository.create()
    try:
        source = await source_repo.get(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")

        # Atomic compare-and-set: only one caller can flip a source to
        # ``syncing`` at a time. Two clicks within the polling window used
        # to enqueue two background tasks; now the second one gets a 409.
        claimed = await source_repo.try_claim_for_sync(source_id)
        if not claimed:
            raise HTTPException(
                status_code=409,
                detail="Source is already syncing; wait for it to finish or fail",
            )
    finally:
        await source_repo.close()

    background_tasks.add_task(_run_ingest, source_id, force)
    return {"status": "started", "source_id": str(source_id), "force": force}


async def _run_ingest(source_id: UUID, force: bool) -> None:
    pipeline: IngestionPipeline | None = None
    try:
        pipeline = await IngestionPipeline.create()
        stats = await pipeline.ingest_source(source_id, force=force)
        log.info("ingest_complete", source_id=str(source_id), stats=stats)
    except Exception as e:  # noqa: BLE001
        log.error("ingest_failed", source_id=str(source_id), error=str(e))
        # The API endpoint flipped the source to ``syncing`` via the CAS
        # claim before kicking off this background task. Once we're inside
        # ``ingest_source`` the pipeline owns status transitions, but if
        # ``IngestionPipeline.create`` raised (or any code before the
        # pipeline took ownership), the row is stuck at ``syncing`` until
        # process restart. Flip it to ``error`` here as a safety net.
        try:
            from src.catalog.source_repo import SourceRepository as _SourceRepository
            from src.catalog.models import SourceStatus as _SourceStatus

            repo = await _SourceRepository.create()
            try:
                await repo.mark_status(
                    source_id,
                    _SourceStatus.ERROR,
                    last_error=f"Ingest crashed: {str(e)[:400]}",
                )
            finally:
                await repo.close()
        except Exception as recover_err:  # noqa: BLE001
            log.warning(
                "ingest_recovery_failed",
                source_id=str(source_id),
                error=str(recover_err)[:200],
            )
    finally:
        # Always release the pipeline pool, even when ``create`` or
        # ``ingest_source`` raised mid-construction.
        if pipeline is not None:
            try:
                await pipeline.close()
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "pipeline_close_failed",
                    source_id=str(source_id),
                    error=str(e)[:200],
                )


@router.post("/sources/validate")
async def validate_source(body: SourceValidateBody) -> dict[str, Any]:
    """Test-connection endpoint used by the new-source wizard.

    For GitLab it runs a minimal unauth-safe call (``/projects/:path``) and
    returns the resolved project(s). For other connectors (path-based
    stubs in Phase 1) it just confirms the declared path exists.
    """
    if body.kind == SourceKind.GITLAB:
        config = SourceConfig(kind="gitlab", name="validate", config=body.config, token=body.token)
        connector = GitLabConnector(config)
        try:
            projects = connector._resolve_projects()  # noqa: SLF001 - intentional reuse
            return {
                "ok": True,
                "kind": body.kind,
                "projects": [
                    {
                        "id": p["id"],
                        "path_with_namespace": p["path_with_namespace"],
                        "web_url": p.get("web_url", ""),
                        "default_branch": p.get("default_branch"),
                    }
                    for p in projects[:20]
                ],
                "total_projects": len(projects),
            }
        except GitLabAPIError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"GitLab validation failed: {e}") from e
        finally:
            connector.close()

    # File-based connectors: check the path exists (can't really validate
    # content without running a full walk).
    from pathlib import Path

    path = body.config.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Config 'path' is required for this connector kind")
    local = Path(path).expanduser()
    if not local.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {local}")
    return {"ok": True, "kind": body.kind, "path": str(local)}


@router.get("/organization/graph")
async def get_organization_graph() -> dict[str, Any]:
    """Aggregated catalog + dependency graph for the organization view.

    One round-trip covers every node + edge the React Flow canvas needs:
    declared orgs, teams, services, and internal service-to-service
    dependencies (``kind = "service"`` rows in ``kg_dependencies``).

    External dependencies (``kind = "external"`` rows -- free-text
    targets like Stripe, Auth0) are intentionally excluded: the graph
    only renders nodes for declared catalog entities. External deps
    are visible only on the originating service's detail page.
    """
    org_repo = await OrgRepository.create()
    team_repo = await TeamRepository.create()
    service_repo = await ServiceRepository.create()
    try:
        orgs = await org_repo.list_all()
        teams = await team_repo.list_all()
        services = await service_repo.list_all()
        dependencies = await service_repo.list_all_dependencies()

        return {
            "orgs": [o.model_dump(mode="json") for o in orgs],
            "teams": [t.model_dump(mode="json") for t in teams],
            "services": [s.model_dump(mode="json") for s in services],
            "dependencies": dependencies,
        }
    finally:
        await service_repo.close()
        await team_repo.close()
        await org_repo.close()


@router.post("/gitlab/projects/search")
async def search_gitlab_projects(body: GitLabProjectSearchBody) -> dict[str, Any]:
    """Paginated project search for the source-wizard dropdown.

    Auth flow: the wizard no longer collects per-source tokens, so this
    endpoint normally falls back to ``PRISM_GITLAB_TOKEN`` (the
    server-side service-account token). A request-body ``token`` is
    still accepted as an admin-only override path (see the Token Policy
    in ``docs/api.md``); when present it's handed to a throwaway
    ``GitLabConnector`` for this one round-trip and never persisted.
    """
    config: dict[str, Any] = {}
    if body.base_url:
        config["base_url"] = body.base_url

    source = SourceConfig(
        kind="gitlab",
        name="project-picker",
        config=config,
        token=body.token,
    )
    connector = GitLabConnector(source)
    try:
        projects, has_more = connector.search_projects(
            body.q,
            page=body.page,
            per_page=body.per_page,
        )
        return {
            "projects": [
                {
                    "id": p["id"],
                    "path_with_namespace": p["path_with_namespace"],
                    "name": p.get("name", ""),
                    "web_url": p.get("web_url", ""),
                    "default_branch": p.get("default_branch"),
                }
                for p in projects
            ],
            "page": body.page,
            "per_page": body.per_page,
            "has_more": has_more,
        }
    except GitLabAPIError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"GitLab project search failed: {e}") from e
    finally:
        connector.close()


@router.post("/gitlab/groups/search")
async def search_gitlab_groups(body: GitLabGroupSearchBody) -> dict[str, Any]:
    """Paginated group search for the source-wizard dropdown (whole-group mode)."""
    config: dict[str, Any] = {}
    if body.base_url:
        config["base_url"] = body.base_url

    source = SourceConfig(
        kind="gitlab",
        name="group-picker",
        config=config,
        token=body.token,
    )
    connector = GitLabConnector(source)
    try:
        groups, has_more = connector.search_groups(
            body.q,
            page=body.page,
            per_page=body.per_page,
        )
        return {
            "groups": [
                {
                    "id": g["id"],
                    "full_path": g.get("full_path") or g.get("path", ""),
                    "name": g.get("name", ""),
                    "web_url": g.get("web_url", ""),
                }
                for g in groups
            ],
            "page": body.page,
            "per_page": body.per_page,
            "has_more": has_more,
        }
    except GitLabAPIError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"GitLab group search failed: {e}") from e
    finally:
        connector.close()
