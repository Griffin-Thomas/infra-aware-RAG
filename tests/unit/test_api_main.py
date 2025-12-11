"""Unit tests for FastAPI main application."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_services():
    """Mock the service initialization."""
    with patch("src.api.main.init_services") as mock_init, patch(
        "src.api.main.cleanup_services"
    ) as mock_cleanup:
        mock_init.return_value = AsyncMock()
        mock_cleanup.return_value = AsyncMock()
        yield mock_init, mock_cleanup


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_readiness_check(self, client):
        """Test readiness check endpoint."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        # Status is "not_ready" when services aren't initialized (e.g., in tests)
        assert data["status"] in ["ready", "not_ready"]
        assert "dependencies" in data
        assert isinstance(data["dependencies"], dict)
        # All expected dependencies should be present
        expected_deps = ["search_engine", "cosmos_db", "graph_db", "resource_service", "terraform_service", "git_service"]
        for dep in expected_deps:
            assert dep in data["dependencies"]

    def test_health_check_returns_json(self, client):
        """Test that health check returns JSON content type."""
        response = client.get("/health")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]


class TestOpenAPIDocumentation:
    """Tests for OpenAPI documentation endpoints."""

    def test_openapi_schema_available(self, client):
        """Test that OpenAPI schema is available."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert data["info"]["title"] == "Infra-Aware RAG API"

    def test_swagger_ui_available(self, client):
        """Test that Swagger UI documentation is available."""
        response = client.get("/docs")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc_ui_available(self, client):
        """Test that ReDoc documentation is available."""
        response = client.get("/redoc")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestCORSMiddleware:
    """Tests for CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present in responses."""
        response = client.get(
            "/health", headers={"Origin": "http://localhost:3000"}
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_preflight_request(self, client):
        """Test CORS preflight OPTIONS request."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers


class TestAPIMetadata:
    """Tests for API metadata and configuration."""

    def test_api_version_in_openapi(self, client):
        """Test that API version is correctly set in OpenAPI schema."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "info" in data
        assert "version" in data["info"]
        # Version should be set from settings (default 1.0.0)
        assert data["info"]["version"]

    def test_api_title_in_openapi(self, client):
        """Test that API title is correctly set."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "Infra-Aware RAG API"

    def test_api_description_in_openapi(self, client):
        """Test that API description is correctly set."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "description" in data["info"]
        assert "Azure infrastructure" in data["info"]["description"]


class TestHealthEndpointTags:
    """Tests for endpoint tagging and organization."""

    def test_health_endpoints_have_tags(self, client):
        """Test that health endpoints are properly tagged."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()

        # Check that health endpoint has correct tag
        health_endpoint = data["paths"]["/health"]["get"]
        assert "tags" in health_endpoint
        assert "health" in health_endpoint["tags"]

        # Check that ready endpoint has correct tag
        ready_endpoint = data["paths"]["/ready"]["get"]
        assert "tags" in ready_endpoint
        assert "health" in ready_endpoint["tags"]
