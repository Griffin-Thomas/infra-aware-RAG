"""Unit tests for the search API router."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.search import router
from src.api.dependencies import get_search_engine
from src.search.models import HybridSearchResults, SearchResult as SearchEngineResult


@pytest.fixture
def mock_search_engine():
    """Create a mock search engine."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def app(mock_search_engine):
    """Create a test FastAPI app with the search router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override the search engine dependency
    test_app.dependency_overrides[get_search_engine] = lambda: mock_search_engine

    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_search_results():
    """Sample search results from the search engine."""
    return HybridSearchResults(
        results=[
            SearchEngineResult(
                id="test-1",
                score=0.95,
                content="This is a test Azure resource",
                doc_type="azure_resource",
                metadata={
                    "name": "test-vm-1",
                    "type": "Microsoft.Compute/virtualMachines",
                    "resource_group": "test-rg",
                },
                highlights=["test Azure <em>resource</em>"],
            ),
            SearchEngineResult(
                id="test-2",
                score=0.85,
                content="This is a test Terraform resource",
                doc_type="terraform_resource",
                metadata={
                    "resource_type": "azurerm_virtual_machine",
                    "resource_name": "test_vm",
                },
                highlights=None,
            ),
        ],
        total_count=2,
        facets={
            "doc_type": {
                "azure_resource": 1,
                "terraform_resource": 1,
            }
        },
    )


class TestSearchEndpoint:
    """Tests for POST /search endpoint."""

    def test_search_basic(self, client, mock_search_engine, sample_search_results):
        """Test basic search with default parameters."""
        mock_search_engine.search.return_value = sample_search_results

        response = client.post(
            "/api/v1/search",
            json={"query": "virtual machine"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "results" in data
        assert "total_count" in data
        assert data["total_count"] == 2
        assert len(data["results"]) == 2

        # Verify first result
        result1 = data["results"][0]
        assert result1["id"] == "test-1"
        assert result1["score"] == 0.95
        assert result1["doc_type"] == "azure_resource"
        assert "test-vm-1" in str(result1["metadata"])

        # Verify search engine was called correctly
        mock_search_engine.search.assert_called_once()
        call_args = mock_search_engine.search.call_args.kwargs
        assert call_args["query"] == "virtual machine"
        assert call_args["mode"] == "hybrid"  # Default
        assert call_args["top"] == 10  # Default

    def test_search_with_mode(self, client, mock_search_engine, sample_search_results):
        """Test search with different modes."""
        mock_search_engine.search.return_value = sample_search_results

        # Test vector mode
        response = client.post(
            "/api/v1/search",
            json={"query": "test query", "mode": "vector"},
        )
        assert response.status_code == 200
        assert mock_search_engine.search.call_args.kwargs["mode"] == "vector"

        # Test keyword mode
        mock_search_engine.reset_mock()
        response = client.post(
            "/api/v1/search",
            json={"query": "test query", "mode": "keyword"},
        )
        assert response.status_code == 200
        assert mock_search_engine.search.call_args.kwargs["mode"] == "keyword"

        # Test hybrid mode (explicit)
        mock_search_engine.reset_mock()
        response = client.post(
            "/api/v1/search",
            json={"query": "test query", "mode": "hybrid"},
        )
        assert response.status_code == 200
        assert mock_search_engine.search.call_args.kwargs["mode"] == "hybrid"

    def test_search_with_doc_types(self, client, mock_search_engine, sample_search_results):
        """Test search with document type filtering."""
        mock_search_engine.search.return_value = sample_search_results

        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "doc_types": ["azure_resource", "terraform_resource"],
            },
        )

        assert response.status_code == 200
        call_args = mock_search_engine.search.call_args.kwargs
        assert call_args["doc_types"] == ["azure_resource", "terraform_resource"]

    def test_search_with_filters(self, client, mock_search_engine, sample_search_results):
        """Test search with custom filters."""
        mock_search_engine.search.return_value = sample_search_results

        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "filters": {"location": "canadaeast", "resource_group": "test-rg"},
            },
        )

        assert response.status_code == 200
        call_args = mock_search_engine.search.call_args.kwargs
        assert call_args["filters"] == {"location": "canadaeast", "resource_group": "test-rg"}

    def test_search_with_top_parameter(self, client, mock_search_engine, sample_search_results):
        """Test search with custom top parameter."""
        mock_search_engine.search.return_value = sample_search_results

        response = client.post(
            "/api/v1/search",
            json={"query": "test", "top": 25},
        )

        assert response.status_code == 200
        assert mock_search_engine.search.call_args.kwargs["top"] == 25

    def test_search_with_facets(self, client, mock_search_engine, sample_search_results):
        """Test search with facets included."""
        mock_search_engine.search.return_value = sample_search_results

        response = client.post(
            "/api/v1/search",
            json={"query": "test", "include_facets": True},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify facets are included
        assert "facets" in data
        assert data["facets"] is not None
        assert "doc_type" in data["facets"]

        # Verify search engine was called with facets enabled
        assert mock_search_engine.search.call_args.kwargs["include_facets"] is True

    def test_search_validation_errors(self, client, mock_search_engine):
        """Test validation errors for invalid requests."""
        # Empty query
        response = client.post(
            "/api/v1/search",
            json={"query": ""},
        )
        assert response.status_code == 422  # Validation error

        # Query too long (> 1000 chars)
        response = client.post(
            "/api/v1/search",
            json={"query": "x" * 1001},
        )
        assert response.status_code == 422

        # Invalid mode
        response = client.post(
            "/api/v1/search",
            json={"query": "test", "mode": "invalid"},
        )
        assert response.status_code == 422

        # Invalid top (< 1)
        response = client.post(
            "/api/v1/search",
            json={"query": "test", "top": 0},
        )
        assert response.status_code == 422

        # Invalid top (> 100)
        response = client.post(
            "/api/v1/search",
            json={"query": "test", "top": 101},
        )
        assert response.status_code == 422

    def test_search_value_error_handling(self, client, mock_search_engine):
        """Test handling of ValueError from search engine (e.g., invalid mode)."""
        mock_search_engine.search.side_effect = ValueError("Invalid search mode")

        response = client.post(
            "/api/v1/search",
            json={"query": "test"},
        )

        assert response.status_code == 400
        assert "Invalid search mode" in response.json()["detail"]

    def test_search_unexpected_error_handling(self, client, mock_search_engine):
        """Test handling of unexpected errors from search engine."""
        mock_search_engine.search.side_effect = Exception("Unexpected error")

        response = client.post(
            "/api/v1/search",
            json={"query": "test"},
        )

        assert response.status_code == 500
        assert "Search failed" in response.json()["detail"]


class TestSearchExpandEndpoint:
    """Tests for POST /search/expand endpoint."""

    def test_expand_basic(self, client, mock_search_engine, sample_search_results):
        """Test basic graph-expanded search."""
        mock_search_engine.search_with_graph_expansion.return_value = sample_search_results

        response = client.post(
            "/api/v1/search/expand",
            json={"query": "virtual machine"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "results" in data
        assert "total_count" in data
        assert data["total_count"] == 2
        assert len(data["results"]) == 2

        # Verify search engine was called correctly
        mock_search_engine.search_with_graph_expansion.assert_called_once()
        call_args = mock_search_engine.search_with_graph_expansion.call_args.kwargs
        assert call_args["query"] == "virtual machine"
        assert call_args["expand_depth"] == 1  # Default
        assert call_args["top"] == 10  # Default

    def test_expand_with_depth(self, client, mock_search_engine, sample_search_results):
        """Test graph expansion with different depths."""
        mock_search_engine.search_with_graph_expansion.return_value = sample_search_results

        # Test depth 1
        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test", "expand_depth": 1},
        )
        assert response.status_code == 200
        assert mock_search_engine.search_with_graph_expansion.call_args.kwargs["expand_depth"] == 1

        # Test depth 2
        mock_search_engine.reset_mock()
        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test", "expand_depth": 2},
        )
        assert response.status_code == 200
        assert mock_search_engine.search_with_graph_expansion.call_args.kwargs["expand_depth"] == 2

        # Test depth 3
        mock_search_engine.reset_mock()
        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test", "expand_depth": 3},
        )
        assert response.status_code == 200
        assert mock_search_engine.search_with_graph_expansion.call_args.kwargs["expand_depth"] == 3

    def test_expand_with_doc_types(self, client, mock_search_engine, sample_search_results):
        """Test graph expansion with document type filtering."""
        mock_search_engine.search_with_graph_expansion.return_value = sample_search_results

        response = client.post(
            "/api/v1/search/expand",
            json={
                "query": "test",
                "doc_types": ["azure_resource"],
            },
        )

        assert response.status_code == 200
        call_args = mock_search_engine.search_with_graph_expansion.call_args.kwargs
        assert call_args["doc_types"] == ["azure_resource"]

    def test_expand_validation_errors(self, client, mock_search_engine):
        """Test validation errors for expand endpoint."""
        # Empty query
        response = client.post(
            "/api/v1/search/expand",
            json={"query": ""},
        )
        assert response.status_code == 422

        # Depth < 1
        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test", "expand_depth": 0},
        )
        assert response.status_code == 422

        # Depth > 3
        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test", "expand_depth": 4},
        )
        assert response.status_code == 422

        # Invalid top
        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test", "top": 101},
        )
        assert response.status_code == 422

    def test_expand_error_handling(self, client, mock_search_engine):
        """Test error handling for graph expansion."""
        mock_search_engine.search_with_graph_expansion.side_effect = Exception(
            "Graph query failed"
        )

        response = client.post(
            "/api/v1/search/expand",
            json={"query": "test"},
        )

        assert response.status_code == 500
        assert "Graph-expanded search failed" in response.json()["detail"]


class TestSearchRouterIntegration:
    """Integration tests for search router with realistic scenarios."""

    def test_empty_results(self, client, mock_search_engine):
        """Test search with no results."""
        mock_search_engine.search.return_value = HybridSearchResults(
            results=[], total_count=0, facets=None
        )

        response = client.post(
            "/api/v1/search",
            json={"query": "nonexistent"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["results"]) == 0

    def test_large_result_set(self, client, mock_search_engine):
        """Test search with maximum allowed results."""
        # Create 100 mock results
        results = [
            SearchEngineResult(
                id=f"test-{i}",
                score=1.0 - (i * 0.01),
                content=f"Test document {i}",
                doc_type="azure_resource",
                metadata={"index": i},
                highlights=None,
            )
            for i in range(100)
        ]

        mock_search_engine.search.return_value = HybridSearchResults(
            results=results,
            total_count=100,
            facets=None,
        )

        response = client.post(
            "/api/v1/search",
            json={"query": "test", "top": 100},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 100
        assert len(data["results"]) == 100

    def test_complex_filters_and_facets(self, client, mock_search_engine, sample_search_results):
        """Test search with complex filters and facets."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "virtual machine",
                "mode": "hybrid",
                "doc_types": ["azure_resource"],
                "filters": {
                    "location": "canadaeast",
                    "resource_group": "prod-rg",
                    "tags": {"environment": "production"},
                },
                "top": 50,
                "include_facets": True,
            },
        )

        # Should succeed (actual validation is in search engine)
        mock_search_engine.search.return_value = sample_search_results
        response = client.post(
            "/api/v1/search",
            json={
                "query": "virtual machine",
                "mode": "hybrid",
                "doc_types": ["azure_resource"],
                "filters": {
                    "location": "canadaeast",
                    "resource_group": "prod-rg",
                },
                "top": 50,
                "include_facets": True,
            },
        )

        assert response.status_code == 200
        call_args = mock_search_engine.search.call_args.kwargs
        assert call_args["query"] == "virtual machine"
        assert call_args["mode"] == "hybrid"
        assert call_args["doc_types"] == ["azure_resource"]
        assert "location" in call_args["filters"]
        assert call_args["top"] == 50
        assert call_args["include_facets"] is True
