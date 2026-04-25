"""API route tests.

The analysis routes and health check don't need a DB because the repository
boundaries are mocked. Catalog routes do need Postgres -- those tests are
gated on ``PRISM_POSTGRES_URL`` / ``PRISM_TEST_POSTGRES_URL`` the same way
``test_catalog.py`` is.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app

PG_URL = os.environ.get("PRISM_TEST_POSTGRES_URL") or os.environ.get("PRISM_POSTGRES_URL")


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_analysis_repo():
    repo = AsyncMock()
    repo.insert = AsyncMock()
    repo.close = AsyncMock()

    with patch("src.api.routes.AnalysisRepository.create", new=AsyncMock(return_value=repo)):
        yield repo


def test_health_check(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "prism-api"


@patch("src.api.routes._run_analysis_task", new_callable=AsyncMock)
def test_analyze_returns_analysis_id(mock_task, client: TestClient, mock_analysis_repo):
    response = client.post(
        "/api/analyze",
        json={"requirement": "Add MFA to customer portal"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "analysis_id" in data
    assert "stream_url" in data
    assert data["stream_url"].startswith("/api/analyze/")


def test_analyze_missing_requirement(client: TestClient):
    response = client.post("/api/analyze", json={})
    assert response.status_code == 422


@patch("src.api.routes._run_analysis_task", new_callable=AsyncMock)
def test_analyze_accepts_structured_context(mock_task, client: TestClient, mock_analysis_repo):
    response = client.post(
        "/api/analyze",
        json={
            "requirement": "Add MFA to customer portal",
            "business_goal": "Reduce account takeover risk before enterprise launch",
            "constraints": "Do not disrupt SSO",
            "known_services": "auth-service, customer-portal",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "analysis_id" in data
    assert "stream_url" in data


def test_report_not_found(client: TestClient):
    response = client.get("/api/analyze/nonexistent-id/report")
    assert response.status_code == 404


# ---------- catalog routes (require Postgres) ----------


@pytest.mark.skipif(PG_URL is None, reason="Set PRISM_POSTGRES_URL to exercise catalog API tests")
def test_org_team_service_source_crud_roundtrip(client: TestClient):
    # Use a unique org name per run so repeated test runs don't collide on
    # the UNIQUE (name) index.
    import uuid as _uuid

    org_name = f"test-org-{_uuid.uuid4().hex[:8]}"

    # Create org
    response = client.post("/api/orgs", json={"name": org_name})
    assert response.status_code == 200, response.text
    org = response.json()
    org_id = org["id"]

    # Create team under org
    response = client.post(
        f"/api/orgs/{org_id}/teams",
        json={"name": "Platform", "description": "Owns the platform"},
    )
    assert response.status_code == 200, response.text
    team = response.json()
    team_id = team["id"]

    # Duplicate team name → 409
    response = client.post(f"/api/orgs/{org_id}/teams", json={"name": "Platform"})
    assert response.status_code == 409

    # Create service under team
    response = client.post(
        f"/api/teams/{team_id}/services",
        json={"name": "auth-service", "repo_url": "https://example.com/auth"},
    )
    assert response.status_code == 200, response.text
    service = response.json()
    service_id = service["id"]

    # List services for team
    response = client.get(f"/api/teams/{team_id}/services")
    assert response.status_code == 200
    assert any(s["id"] == service_id for s in response.json()["services"])

    # Create a source at service scope
    response = client.post(
        "/api/sources",
        json={
            "scope": "service",
            "scope_id": service_id,
            "kind": "gitlab",
            "name": "auth gitlab",
            "config": {"project_path": "org/auth"},
            "token": "glpat-test",
        },
    )
    assert response.status_code == 200, response.text
    source = response.json()
    source_id = source["id"]

    # List sources filtered by service
    response = client.get(f"/api/sources?service_id={service_id}")
    assert response.status_code == 200
    assert any(s["id"] == source_id for s in response.json()["sources"])

    # Delete source (also cleans up OpenSearch side; best-effort)
    response = client.delete(f"/api/sources/{source_id}")
    assert response.status_code == 200

    # Delete service, team, org to leave the DB clean
    assert client.delete(f"/api/services/{service_id}").status_code == 200
    assert client.delete(f"/api/teams/{team_id}").status_code == 200
    assert client.delete(f"/api/orgs/{org_id}").status_code == 200


def test_source_delete_aborts_on_opensearch_failure(client: TestClient):
    """Round-6 fix: source delete used to log-and-ignore OpenSearch
    cleanup failures, dropping the Postgres handle anyway and leaving
    chunks orphaned with stale source/org/team/service metadata.

    Now it abort-patterns: clean OS first, return 503 if cleanup
    fails, and keep the source row intact for retry. The test stubs
    ``SourceRepository.create`` + ``delete_by_source_id`` so it
    doesn't need Postgres -- the abort behavior is purely a route-level
    contract.
    """
    import uuid as _uuid
    from src.api import catalog_routes

    fake_source_id = _uuid.uuid4()

    class _FakeSource:
        id = fake_source_id
        name = "stub-source"
        org_id = None
        team_id = None
        service_id = _uuid.uuid4()

    fake_repo = AsyncMock()
    fake_repo.get = AsyncMock(return_value=_FakeSource())
    fake_repo.delete = AsyncMock(return_value=True)
    fake_repo.close = AsyncMock()

    def _boom(*_args, **_kwargs):  # noqa: ANN001
        raise RuntimeError("simulated OpenSearch outage")

    # Round 1: OS down -> abort with 503, source.delete must NOT be
    # called (we'd be dropping the only handle on the chunks).
    with patch.object(
        catalog_routes.SourceRepository,
        "create",
        new=AsyncMock(return_value=fake_repo),
    ), patch.object(catalog_routes, "delete_by_source_id", side_effect=_boom):
        resp = client.delete(f"/api/sources/{fake_source_id}")
        assert resp.status_code == 503, resp.text
        assert "OpenSearch cleanup failed" in resp.json()["detail"]
    fake_repo.delete.assert_not_called()

    # Round 2: OS recovers -> retry succeeds, delete actually runs.
    with patch.object(
        catalog_routes.SourceRepository,
        "create",
        new=AsyncMock(return_value=fake_repo),
    ), patch.object(catalog_routes, "delete_by_source_id", return_value=0):
        resp = client.delete(f"/api/sources/{fake_source_id}")
        assert resp.status_code == 200, resp.text
    fake_repo.delete.assert_awaited_once()
