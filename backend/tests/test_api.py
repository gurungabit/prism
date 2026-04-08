from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from src.main import app


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
