"""Unit tests for Tools API router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.routers.tools import router
from src.api.dependencies import (
    get_search_engine,
    get_resource_service,
    get_terraform_service,
    get_git_service,
)
from src.search.models import HybridSearchResults, SearchResult
from src.api.models.resources import AzureResource, TerraformLink, ResourceDependency
from src.api.models.terraform import TerraformResource, TerraformPlan, PlanAnalysis
from src.api.models.git import GitCommit, FileChange


@pytest.fixture
def mock_search_engine():
    """Create mock search engine."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_resource_service():
    """Create mock resource service."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_terraform_service():
    """Create mock Terraform service."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_git_service():
    """Create mock Git service."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def app(mock_search_engine, mock_resource_service, mock_terraform_service, mock_git_service):
    """Create test FastAPI app with tools router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override dependencies
    test_app.dependency_overrides[get_search_engine] = lambda: mock_search_engine
    test_app.dependency_overrides[get_resource_service] = lambda: mock_resource_service
    test_app.dependency_overrides[get_terraform_service] = lambda: mock_terraform_service
    test_app.dependency_overrides[get_git_service] = lambda: mock_git_service

    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestListTools:
    """Tests for GET /tools endpoint."""

    def test_list_tools(self, client):
        """Test listing all available tools."""
        response = client.get("/api/v1/tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    def test_list_tools_structure(self, client):
        """Test that tools have required structure."""
        response = client.get("/api/v1/tools")
        data = response.json()

        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)
            assert isinstance(tool["parameters"], dict)

    def test_list_tools_contains_expected_tools(self, client):
        """Test that expected tools are present."""
        response = client.get("/api/v1/tools")
        data = response.json()

        tool_names = [tool["name"] for tool in data["tools"]]
        assert "search_infrastructure" in tool_names
        assert "get_resource_details" in tool_names
        assert "get_terraform_plan" in tool_names
        assert "get_git_history" in tool_names


class TestExecuteSearchInfrastructure:
    """Tests for executing search_infrastructure tool."""

    def test_execute_search_infrastructure(self, client, mock_search_engine):
        """Test executing search_infrastructure tool."""
        # Mock search results
        mock_search_engine.search.return_value = HybridSearchResults(
            results=[
                SearchResult(
                    id="test-1",
                    score=0.95,
                    content="Test Azure VM",
                    doc_type="azure_resource",
                    metadata={"name": "test-vm"},
                    highlights=None,
                )
            ],
            total_count=1,
            facets=None,
        )

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "search_infrastructure",
                "arguments": {"query": "virtual machines"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "search_infrastructure"
        assert data["error"] is None
        assert "result" in data
        assert data["result"]["total_count"] == 1
        assert len(data["result"]["results"]) == 1

    def test_execute_search_with_filters(self, client, mock_search_engine):
        """Test search with filters and doc types."""
        mock_search_engine.search.return_value = HybridSearchResults(
            results=[],
            total_count=0,
            facets=None,
        )

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "search_infrastructure",
                "arguments": {
                    "query": "storage accounts",
                    "doc_types": ["azure_resource"],
                    "filters": {"location": "canadaeast"},
                    "top": 5,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None

        # Verify search was called with correct arguments
        mock_search_engine.search.assert_called_once()
        call_args = mock_search_engine.search.call_args
        assert call_args.kwargs["query"] == "storage accounts"
        assert call_args.kwargs["doc_types"] == ["azure_resource"]
        assert call_args.kwargs["filters"] == {"location": "canadaeast"}
        assert call_args.kwargs["top"] == 5


class TestExecuteResourceTools:
    """Tests for executing resource-related tools."""

    def test_execute_get_resource_details(self, client, mock_resource_service):
        """Test executing get_resource_details tool."""
        mock_resource_service.get_resource.return_value = AzureResource(
            id="/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            name="test-vm",
            type="Microsoft.Compute/virtualMachines",
            resource_group="rg",
            subscription_id="xxx",
            subscription_name="Production",
            location="canadaeast",
            tags={},
            properties={},
        )

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_details",
                "arguments": {
                    "resource_id": "/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm"
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "get_resource_details"
        assert data["error"] is None
        assert data["result"]["name"] == "test-vm"

    def test_execute_get_resource_not_found(self, client, mock_resource_service):
        """Test get_resource_details when resource not found."""
        mock_resource_service.get_resource.return_value = None

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_details",
                "arguments": {"resource_id": "/nonexistent"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "get_resource_details"
        assert data["error"] is not None
        assert "not found" in data["error"].lower()

    def test_execute_get_resource_terraform(self, client, mock_resource_service):
        """Test executing get_resource_terraform tool."""
        mock_resource_service.get_terraform_for_resource.return_value = [
            TerraformLink(
                address="azurerm_virtual_machine.test",
                type="azurerm_virtual_machine",
                file_path="main.tf",
                line_number=10,
                repo_url="https://github.com/example/infra",
                branch="main",
                source_code="resource \"azurerm_virtual_machine\" \"test\" { ... }",
            )
        ]

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_terraform",
                "arguments": {"resource_id": "/subscriptions/xxx/..."},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert isinstance(data["result"], list)
        assert len(data["result"]) == 1

    def test_execute_get_resource_dependencies(self, client, mock_resource_service):
        """Test executing get_resource_dependencies tool."""
        mock_resource_service.get_dependencies.return_value = [
            ResourceDependency(
                id="/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet",
                name="vnet",
                type="Microsoft.Network/virtualNetworks",
                relationship="depends_on",
                direction="upstream",
            )
        ]

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_dependencies",
                "arguments": {
                    "resource_id": "/subscriptions/xxx/...",
                    "direction": "both",
                    "depth": 2,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert isinstance(data["result"], list)

    def test_execute_query_resource_graph(self, client, mock_resource_service):
        """Test executing query_resource_graph tool."""
        mock_resource_service.execute_resource_graph_query.return_value = [
            {"name": "vm1", "type": "Microsoft.Compute/virtualMachines"},
            {"name": "vm2", "type": "Microsoft.Compute/virtualMachines"},
        ]

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "query_resource_graph",
                "arguments": {
                    "query": "Resources | where type == 'microsoft.compute/virtualmachines' | project name, type"
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "results" in data["result"]


class TestExecuteTerraformTools:
    """Tests for executing Terraform-related tools."""

    def test_execute_list_terraform_resources(self, client, mock_terraform_service):
        """Test executing list_terraform_resources tool."""
        mock_terraform_service.list_resources.return_value = [
            TerraformResource(
                address="azurerm_virtual_machine.test",
                type="azurerm_virtual_machine",
                name="test",
                module_path=None,
                file_path="main.tf",
                line_number=10,
                repo_url="https://github.com/example/infra",
                branch="main",
                provider="azurerm",
                source_code="resource \"azurerm_virtual_machine\" \"test\" { ... }",
                dependencies=[],
                azure_resource_id=None,
            )
        ]

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "list_terraform_resources",
                "arguments": {"repo_url": "https://github.com/example/infra"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert isinstance(data["result"], list)

    def test_execute_get_terraform_plan(self, client, mock_terraform_service):
        """Test executing get_terraform_plan tool."""
        from datetime import datetime, timezone

        mock_terraform_service.get_plan.return_value = TerraformPlan(
            id="plan-123",
            repo_url="https://github.com/example/infra",
            branch="main",
            commit_sha="abc123",
            timestamp=datetime.now(timezone.utc),
            add=5,
            change=2,
            destroy=1,
            changes=[],
        )

        response = client.post(
            "/api/v1/tools/execute",
            json={"name": "get_terraform_plan", "arguments": {"plan_id": "plan-123"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["result"]["id"] == "plan-123"

    def test_execute_analyze_terraform_plan(self, client, mock_terraform_service):
        """Test executing analyze_terraform_plan tool."""
        from datetime import datetime, timezone

        mock_terraform_service.get_plan.return_value = TerraformPlan(
            id="plan-123",
            repo_url="https://github.com/example/infra",
            branch="main",
            commit_sha="abc123",
            timestamp=datetime.now(timezone.utc),
            add=5,
            change=2,
            destroy=1,
            changes=[],
        )

        mock_terraform_service.analyze_plan.return_value = PlanAnalysis(
            summary="Plan will create 5 resources",
            risk_level="medium",
            key_changes=["Create VMs", "Update networking"],
            recommendations=["Review VM sizes", "Check network security groups"],
        )

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "analyze_terraform_plan",
                "arguments": {"plan_id": "plan-123"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["result"]["risk_level"] == "medium"


class TestExecuteGitTools:
    """Tests for executing Git-related tools."""

    def test_execute_get_git_history(self, client, mock_git_service):
        """Test executing get_git_history tool."""
        from datetime import datetime, timezone

        mock_git_service.list_commits.return_value = [
            GitCommit(
                sha="abc123def456",
                short_sha="abc123d",
                repo_url="https://github.com/example/infra",
                branch="main",
                message="Update networking",
                author_name="John Doe",
                author_email="john@example.com",
                commit_date=datetime.now(timezone.utc),
                files_changed=[],
                terraform_files=[],
                has_terraform_changes=False,
            )
        ]

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_git_history",
                "arguments": {"repo_url": "https://github.com/example/infra", "limit": 10},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert isinstance(data["result"], list)

    def test_execute_get_commit_details(self, client, mock_git_service):
        """Test executing get_commit_details tool."""
        from datetime import datetime, timezone

        mock_git_service.get_commit.return_value = GitCommit(
            sha="abc123def456",
            short_sha="abc123d",
            repo_url="https://github.com/example/infra",
            branch="main",
            message="Update networking",
            author_name="John Doe",
            author_email="john@example.com",
            commit_date=datetime.now(timezone.utc),
            files_changed=[
                FileChange(
                    path="network/main.tf",
                    change_type="modify",
                    additions=10,
                    deletions=5,
                )
            ],
            terraform_files=["network/main.tf"],
            has_terraform_changes=True,
        )

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_commit_details",
                "arguments": {
                    "sha": "abc123d",
                    "repo_url": "https://github.com/example/infra",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["result"]["sha"] == "abc123def456"


class TestToolValidation:
    """Tests for tool call validation."""

    def test_execute_unknown_tool(self, client):
        """Test executing an unknown tool."""
        response = client.post(
            "/api/v1/tools/execute",
            json={"name": "unknown_tool", "arguments": {}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "unknown_tool"
        assert data["error"] is not None
        assert "unknown tool" in data["error"].lower()

    def test_execute_missing_required_argument(self, client):
        """Test executing tool with missing required argument."""
        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "search_infrastructure",
                "arguments": {},  # Missing required 'query'
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "query" in data["error"].lower()

    def test_execute_unexpected_argument(self, client):
        """Test executing tool with unexpected argument."""
        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_details",
                "arguments": {
                    "resource_id": "/subscriptions/xxx/...",
                    "unexpected_param": "value",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "unexpected" in data["error"].lower()


class TestErrorHandling:
    """Tests for error handling."""

    def test_execute_tool_service_exception(self, client, mock_search_engine):
        """Test handling of service exceptions."""
        mock_search_engine.search.side_effect = Exception("Database connection failed")

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "search_infrastructure",
                "arguments": {"query": "test"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "failed" in data["error"].lower()

    def test_execute_list_subscriptions_no_params(self, client, mock_resource_service):
        """Test tool with no parameters."""
        mock_resource_service.list_subscriptions.return_value = [
            {"id": "sub-1", "name": "Production"},
            {"id": "sub-2", "name": "Development"},
        ]

        response = client.post(
            "/api/v1/tools/execute",
            json={"name": "list_subscriptions", "arguments": {}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "subscriptions" in data["result"]
