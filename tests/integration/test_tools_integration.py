"""Integration tests for Tools API router.

These tests verify end-to-end tool execution flow through the FastAPI application,
testing the integration between routers, services, and backend systems.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    """Create mock search engine with realistic behaviour."""
    mock = AsyncMock()
    mock.search.return_value = HybridSearchResults(
        results=[
            SearchResult(
                id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1",
                score=0.95,
                content="Virtual machine in production environment with managed disks",
                doc_type="azure_resource",
                metadata={
                    "name": "vm1",
                    "type": "Microsoft.Compute/virtualMachines",
                    "location": "canadaeast",
                },
                highlights=None,
            ),
            SearchResult(
                id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/vnet1",
                score=0.85,
                content="Virtual network with 3 subnets",
                doc_type="azure_resource",
                metadata={
                    "name": "vnet1",
                    "type": "Microsoft.Network/virtualNetworks",
                    "location": "canadaeast",
                },
                highlights=None,
            ),
        ],
        total_count=2,
        facets=None,
    )
    return mock


@pytest.fixture
def mock_resource_service():
    """Create mock resource service with realistic behaviour."""
    mock = AsyncMock()

    # get_resource returns an Azure resource
    mock.get_resource.return_value = AzureResource(
        id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1",
        name="vm1",
        type="Microsoft.Compute/virtualMachines",
        resource_group="test-rg",
        subscription_id="test-sub",
        subscription_name="Production",
        location="canadaeast",
        tags={"environment": "prod", "owner": "platform-team"},
        properties={
            "vmSize": "Standard_D4s_v3",
            "osType": "Linux",
            "provisioningState": "Succeeded",
        },
    )

    # get_terraform_for_resource returns Terraform links
    mock.get_terraform_for_resource.return_value = [
        TerraformLink(
            address="azurerm_virtual_machine.vm1",
            type="azurerm_virtual_machine",
            file_path="compute/main.tf",
            line_number=42,
            repo_url="https://github.com/example/infra",
            branch="main",
            source_code='resource "azurerm_virtual_machine" "vm1" {\n  name = "vm1"\n  location = "canadaeast"\n}',
        )
    ]

    # get_dependencies returns resource dependencies
    mock.get_dependencies.return_value = [
        ResourceDependency(
            id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/vnet1",
            name="vnet1",
            type="Microsoft.Network/virtualNetworks",
            relationship="depends_on",
            direction="upstream",
        ),
        ResourceDependency(
            id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Storage/storageAccounts/storage1",
            name="storage1",
            type="Microsoft.Storage/storageAccounts",
            relationship="uses",
            direction="downstream",
        ),
    ]

    # execute_resource_graph_query returns query results
    mock.execute_resource_graph_query.return_value = [
        {"name": "vm1", "type": "Microsoft.Compute/virtualMachines", "location": "canadaeast"},
        {"name": "vm2", "type": "Microsoft.Compute/virtualMachines", "location": "canadacentral"},
    ]

    # list_subscriptions returns subscription list
    mock.list_subscriptions.return_value = [
        {"id": "sub-1", "name": "Production"},
        {"id": "sub-2", "name": "Development"},
    ]

    # get_resource_types_summary returns resource type summary
    mock.get_resource_types_summary.return_value = [
        {"type": "Microsoft.Compute/virtualMachines", "count": 25},
        {"type": "Microsoft.Network/virtualNetworks", "count": 10},
        {"type": "Microsoft.Storage/storageAccounts", "count": 15},
    ]

    return mock


@pytest.fixture
def mock_terraform_service():
    """Create mock Terraform service with realistic behaviour."""
    mock = AsyncMock()

    # list_resources returns Terraform resources
    mock.list_resources.return_value = [
        TerraformResource(
            address="azurerm_virtual_machine.vm1",
            type="azurerm_virtual_machine",
            name="vm1",
            module_path=None,
            file_path="compute/main.tf",
            line_number=42,
            repo_url="https://github.com/example/infra",
            branch="main",
            provider="azurerm",
            source_code='resource "azurerm_virtual_machine" "vm1" { ... }',
            dependencies=["azurerm_network_interface.nic1"],
            azure_resource_id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1",
        ),
    ]

    # get_resource returns a specific Terraform resource
    mock.get_resource.return_value = TerraformResource(
        address="azurerm_virtual_machine.vm1",
        type="azurerm_virtual_machine",
        name="vm1",
        module_path=None,
        file_path="compute/main.tf",
        line_number=42,
        repo_url="https://github.com/example/infra",
        branch="main",
        provider="azurerm",
        source_code='resource "azurerm_virtual_machine" "vm1" { ... }',
        dependencies=["azurerm_network_interface.nic1"],
        azure_resource_id="/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1",
    )

    # get_plan returns a Terraform plan
    mock.get_plan.return_value = TerraformPlan(
        id="plan-123",
        repo_url="https://github.com/example/infra",
        branch="main",
        commit_sha="abc123def456",
        timestamp=datetime.now(timezone.utc),
        add=5,
        change=2,
        destroy=1,
        changes=[],
    )

    # analyze_plan returns plan analysis
    mock.analyze_plan.return_value = PlanAnalysis(
        summary="Plan will create 5 new resources, modify 2 existing resources, and destroy 1 resource",
        risk_level="medium",
        key_changes=[
            "Create 3 new virtual machines",
            "Update network security group rules",
            "Destroy unused storage account",
        ],
        recommendations=[
            "Review VM sizes to ensure cost efficiency",
            "Verify network security group changes don't block required traffic",
            "Ensure storage account is backed up before destruction",
        ],
    )

    return mock


@pytest.fixture
def mock_git_service():
    """Create mock Git service with realistic behaviour."""
    mock = AsyncMock()

    # list_commits returns commit history
    mock.list_commits.return_value = [
        GitCommit(
            sha="abc123def456",
            short_sha="abc123d",
            repo_url="https://github.com/example/infra",
            branch="main",
            message="Update networking configuration for production",
            author_name="John Doe",
            author_email="john@example.com",
            commit_date=datetime.now(timezone.utc),
            files_changed=[
                FileChange(path="network/main.tf", change_type="modify", additions=10, deletions=5),
                FileChange(path="network/variables.tf", change_type="modify", additions=2, deletions=1),
            ],
            terraform_files=["network/main.tf", "network/variables.tf"],
            has_terraform_changes=True,
        ),
        GitCommit(
            sha="def456ghi789",
            short_sha="def456g",
            repo_url="https://github.com/example/infra",
            branch="main",
            message="Add new VM resources",
            author_name="Jane Smith",
            author_email="jane@example.com",
            commit_date=datetime.now(timezone.utc),
            files_changed=[
                FileChange(path="compute/main.tf", change_type="add", additions=50, deletions=0),
            ],
            terraform_files=["compute/main.tf"],
            has_terraform_changes=True,
        ),
    ]

    # get_commit returns commit details
    mock.get_commit.return_value = GitCommit(
        sha="abc123def456",
        short_sha="abc123d",
        repo_url="https://github.com/example/infra",
        branch="main",
        message="Update networking configuration for production",
        author_name="John Doe",
        author_email="john@example.com",
        commit_date=datetime.now(timezone.utc),
        files_changed=[
            FileChange(
                path="network/main.tf",
                change_type="modify",
                additions=15,
                deletions=5,
            ),
            FileChange(
                path="network/variables.tf",
                change_type="modify",
                additions=3,
                deletions=1,
            ),
        ],
        terraform_files=["network/main.tf", "network/variables.tf"],
        has_terraform_changes=True,
    )

    return mock


@pytest.fixture
def app(mock_search_engine, mock_resource_service, mock_terraform_service, mock_git_service):
    """Create test FastAPI app with all dependencies."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override all dependencies
    test_app.dependency_overrides[get_search_engine] = lambda: mock_search_engine
    test_app.dependency_overrides[get_resource_service] = lambda: mock_resource_service
    test_app.dependency_overrides[get_terraform_service] = lambda: mock_terraform_service
    test_app.dependency_overrides[get_git_service] = lambda: mock_git_service

    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.mark.integration
class TestEndToEndToolExecution:
    """Integration tests for end-to-end tool execution."""

    def test_search_and_get_details_workflow(self, client, mock_search_engine, mock_resource_service):
        """Test workflow: search for resources, then get details."""
        # Step 1: Search for resources
        search_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "search_infrastructure",
                "arguments": {"query": "virtual machines in production"},
            },
        )

        assert search_response.status_code == 200
        search_data = search_response.json()
        assert search_data["error"] is None
        assert len(search_data["result"]["results"]) > 0

        # Extract resource ID from search results
        resource_id = search_data["result"]["results"][0]["id"]

        # Step 2: Get details for the first resource
        details_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_details",
                "arguments": {"resource_id": resource_id},
            },
        )

        assert details_response.status_code == 200
        details_data = details_response.json()
        assert details_data["error"] is None
        assert details_data["result"]["name"] == "vm1"
        assert details_data["result"]["location"] == "canadaeast"

    def test_resource_terraform_and_git_workflow(self, client, mock_resource_service, mock_git_service):
        """Test workflow: get resource, find Terraform code, check Git history."""
        resource_id = "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1"

        # Step 1: Get Terraform code for resource
        terraform_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_terraform",
                "arguments": {"resource_id": resource_id},
            },
        )

        assert terraform_response.status_code == 200
        terraform_data = terraform_response.json()
        assert terraform_data["error"] is None
        assert len(terraform_data["result"]) > 0

        # Extract repo URL from Terraform link
        repo_url = terraform_data["result"][0]["repo_url"]

        # Step 2: Get Git history for the repo
        git_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_git_history",
                "arguments": {"repo_url": repo_url, "limit": 10},
            },
        )

        assert git_response.status_code == 200
        git_data = git_response.json()
        assert git_data["error"] is None
        assert len(git_data["result"]) > 0
        assert git_data["result"][0]["has_terraform_changes"] is True

    def test_terraform_plan_analysis_workflow(self, client, mock_terraform_service):
        """Test workflow: get Terraform plan, then analyze it."""
        plan_id = "plan-123"

        # Step 1: Get plan details
        plan_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_terraform_plan",
                "arguments": {"plan_id": plan_id},
            },
        )

        assert plan_response.status_code == 200
        plan_data = plan_response.json()
        assert plan_data["error"] is None
        assert plan_data["result"]["id"] == plan_id
        assert plan_data["result"]["add"] == 5

        # Step 2: Analyze the plan
        analysis_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "analyze_terraform_plan",
                "arguments": {"plan_id": plan_id},
            },
        )

        assert analysis_response.status_code == 200
        analysis_data = analysis_response.json()
        assert analysis_data["error"] is None
        assert analysis_data["result"]["risk_level"] == "medium"
        assert len(analysis_data["result"]["key_changes"]) > 0
        assert len(analysis_data["result"]["recommendations"]) > 0

    def test_resource_dependencies_workflow(self, client, mock_resource_service):
        """Test workflow: get resource dependencies."""
        resource_id = "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1"

        # Get dependencies
        deps_response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_dependencies",
                "arguments": {
                    "resource_id": resource_id,
                    "direction": "both",
                    "depth": 2,
                },
            },
        )

        assert deps_response.status_code == 200
        deps_data = deps_response.json()
        assert deps_data["error"] is None
        assert len(deps_data["result"]) > 0

        # Verify dependency structure
        for dep in deps_data["result"]:
            assert "id" in dep
            assert "name" in dep
            assert "type" in dep
            assert "relationship" in dep
            assert "direction" in dep
            assert dep["direction"] in ["upstream", "downstream"]


@pytest.mark.integration
class TestErrorHandling:
    """Integration tests for error handling scenarios."""

    def test_resource_not_found_error(self, client, mock_resource_service):
        """Test handling when resource is not found."""
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
        assert data["error"] is not None
        assert "not found" in data["error"].lower()

    def test_terraform_plan_not_found_error(self, client, mock_terraform_service):
        """Test handling when Terraform plan is not found."""
        mock_terraform_service.get_plan.return_value = None

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_terraform_plan",
                "arguments": {"plan_id": "nonexistent-plan"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "not found" in data["error"].lower()

    def test_git_commit_not_found_error(self, client, mock_git_service):
        """Test handling when Git commit is not found."""
        mock_git_service.get_commit.return_value = None

        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_commit_details",
                "arguments": {
                    "sha": "nonexistent",
                    "repo_url": "https://github.com/example/infra",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "not found" in data["error"].lower()

    def test_service_exception_handling(self, client, mock_search_engine):
        """Test handling of service exceptions."""
        mock_search_engine.search.side_effect = Exception("Database connection timeout")

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


@pytest.mark.integration
class TestToolValidation:
    """Integration tests for tool validation."""

    def test_missing_required_parameter(self, client):
        """Test validation of missing required parameters."""
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

    def test_unexpected_parameter(self, client):
        """Test validation of unexpected parameters."""
        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "get_resource_details",
                "arguments": {
                    "resource_id": "/test",
                    "unexpected_param": "value",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "unexpected" in data["error"].lower()

    def test_unknown_tool(self, client):
        """Test validation of unknown tool names."""
        response = client.post(
            "/api/v1/tools/execute",
            json={
                "name": "nonexistent_tool",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "unknown" in data["error"].lower()


@pytest.mark.integration
class TestListTools:
    """Integration tests for listing tools."""

    def test_list_tools_endpoint(self, client):
        """Test listing all available tools."""
        response = client.get("/api/v1/tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) == 13

        # Verify tool structure
        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert isinstance(tool["parameters"], dict)
            assert "type" in tool["parameters"]
            assert "properties" in tool["parameters"]
            # "required" field is optional - only present if tool has required parameters
