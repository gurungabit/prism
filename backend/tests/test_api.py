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
