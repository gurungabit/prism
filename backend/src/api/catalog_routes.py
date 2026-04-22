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
    repo = await OrgRepository.create()
    try:
        deleted = await repo.delete(org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Organization not found")
        return {"status": "deleted", "org_id": str(org_id)}
    finally:
        await repo.close()


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
    repo = await TeamRepository.create()
    try:
        deleted = await repo.delete(team_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Team not found")
        return {"status": "deleted", "team_id": str(team_id)}
    finally:
        await repo.close()


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

        # Newly declared service might satisfy parked dependency edges. Walk
        # ``kg_pending_dependencies`` for this name and promote matching rows.
        reconciled = await service_repo.reconcile_pending_dependencies(service.id, service.name)
        if reconciled:
            log.info(
                "pending_dependencies_reconciled",
                service=service.name,
                count=reconciled,
            )
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
    repo = await ServiceRepository.create()
    try:
        deleted = await repo.delete(service_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Service not found")
        return {"status": "deleted", "service_id": str(service_id)}
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
        # Remove every chunk indexed under this source before deleting the
        # row itself. ``ON DELETE CASCADE`` handles the Postgres side
        # (kg_documents, document_registry, source_secrets), but OpenSearch
        # is a separate store so we have to clean it up explicitly.
        try:
            delete_by_source_id(source_id, get_opensearch_client())
        except Exception as e:  # noqa: BLE001
            log.warning("opensearch_cleanup_failed", source_id=str(source_id), error=str(e)[:200])

        deleted = await source_repo.delete(source_id)
        if not deleted:
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

        # Flip to 'syncing' immediately so the UI reflects the click even
        # before the background task starts pulling documents. The pipeline
        # flips it again on entry, but this eliminates the UI's flicker.
        await source_repo.mark_status(source_id, SourceStatus.SYNCING, last_error=None)
    finally:
        await source_repo.close()

    background_tasks.add_task(_run_ingest, source_id, force)
    return {"status": "started", "source_id": str(source_id), "force": force}


async def _run_ingest(source_id: UUID, force: bool) -> None:
    try:
        pipeline = await IngestionPipeline.create()
        stats = await pipeline.ingest_source(source_id, force=force)
        log.info("ingest_complete", source_id=str(source_id), stats=stats)
        await pipeline.close()
    except Exception as e:  # noqa: BLE001
        log.error("ingest_failed", source_id=str(source_id), error=str(e))


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
    orgs, teams, services, service-to-service dependencies, and pending
    (un-declared target) dependencies. Pending deps surface as orphan target
    nodes so the user can see missing services without a separate call.
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

    The wizard's token isn't saved yet -- it sits in React state -- so this
    endpoint accepts the token inline (POST body, not query string) and hands
    it to a throwaway ``GitLabConnector`` purely for this one API round-trip.
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
