"""Unit tests for the resources API router."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.resources import router
from src.api.dependencies import get_resource_service, get_graph_builder
from src.api.models.resources import AzureResource, TerraformLink


@pytest.fixture
def mock_resource_service():
    """Create a mock resource service."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_graph_builder():
    """Create a mock graph builder."""
    # Graph builder methods are synchronous, so use MagicMock
    mock = MagicMock()
    return mock


@pytest.fixture
def app(mock_resource_service, mock_graph_builder):
    """Create a test FastAPI app with the resources router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override dependencies
    test_app.dependency_overrides[get_resource_service] = lambda: mock_resource_service
    test_app.dependency_overrides[get_graph_builder] = lambda: mock_graph_builder

    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_azure_resource():
    """Sample Azure resource."""
    return AzureResource(
        id="/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        name="test-vm",
        type="Microsoft.Compute/virtualMachines",
        resource_group="test-rg",
        subscription_id="sub-123",
        subscription_name="Test Subscription",
        location="canadaeast",
        tags={"environment": "test", "owner": "team"},
        sku={"name": "Standard_D2s_v3"},
        kind=None,
        properties={
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "osProfile": {"computerName": "test-vm"},
        },
    )


@pytest.fixture
def sample_terraform_link():
    """Sample Terraform link."""
    return TerraformLink(
        address="azurerm_virtual_machine.test_vm",
        type="azurerm_virtual_machine",
        file_path="infrastructure/compute.tf",
        line_number=42,
        repo_url="https://github.com/org/repo",
        branch="main",
        source_code='resource "azurerm_virtual_machine" "test_vm" {\n  name = "test-vm"\n}',
    )


class TestGetResourceEndpoint:
    """Tests for GET /resources/{resource_id} endpoint."""

    def test_get_resource_success(self, client, mock_resource_service, sample_azure_resource):
        """Test successful resource retrieval."""
        mock_resource_service.get_resource.return_value = sample_azure_resource

        # URL encode the resource ID
        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        response = client.get(f"/api/v1/resources{resource_id}")

        assert response.status_code == 200
        data = response.json()

        # Verify response data
        assert data["id"] == sample_azure_resource.id
        assert data["name"] == "test-vm"
        assert data["type"] == "Microsoft.Compute/virtualMachines"
        assert data["resource_group"] == "test-rg"
        assert data["location"] == "canadaeast"
        assert data["tags"]["environment"] == "test"

    def test_get_resource_not_found(self, client, mock_resource_service):
        """Test resource not found."""
        mock_resource_service.get_resource.return_value = None

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/nonexistent"
        response = client.get(f"/api/v1/resources{resource_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_resource_url_decoding(self, client, mock_resource_service, sample_azure_resource):
        """Test that resource IDs are properly URL decoded."""
        mock_resource_service.get_resource.return_value = sample_azure_resource

        # Test with URL-encoded slashes (%2F)
        encoded_id = "%2Fsubscriptions%2Fsub-123%2FresourceGroups%2Ftest-rg%2Fproviders%2FMicrosoft.Compute%2FvirtualMachines%2Ftest-vm"
        response = client.get(f"/api/v1/resources/{encoded_id}")

        assert response.status_code == 200

        # Verify service was called with decoded ID
        call_args = mock_resource_service.get_resource.call_args[0]
        assert "/" in call_args[0]  # Should contain decoded slashes


class TestGetTerraformForResourceEndpoint:
    """Tests for GET /resources/{resource_id}/terraform endpoint."""

    def test_get_terraform_links_success(
        self, client, mock_resource_service, mock_graph_builder, sample_terraform_link
    ):
        """Test successful Terraform link retrieval."""
        # Mock graph builder response
        mock_graph_builder.find_terraform_for_resource.return_value = [
            {"address": "azurerm_virtual_machine.test_vm"}
        ]

        # Configure the mock to return the sample model when awaited
        async def mock_get_terraform(address):
            if address == "azurerm_virtual_machine.test_vm":
                return sample_terraform_link
            return None

        mock_resource_service.get_terraform_resource = mock_get_terraform

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        response = client.get(f"/api/v1/resources{resource_id}/terraform")

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert len(data) == 1
        assert data[0]["address"] == "azurerm_virtual_machine.test_vm"
        assert data[0]["file_path"] == "infrastructure/compute.tf"
        assert data[0]["line_number"] == 42

    def test_get_terraform_links_empty(self, client, mock_graph_builder, mock_resource_service):
        """Test when no Terraform links are found."""
        mock_graph_builder.find_terraform_for_resource.return_value = []

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        response = client.get(f"/api/v1/resources{resource_id}/terraform")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_terraform_links_error(self, client, mock_graph_builder):
        """Test error handling for Terraform link retrieval."""
        mock_graph_builder.find_terraform_for_resource.side_effect = Exception("Graph error")

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        response = client.get(f"/api/v1/resources{resource_id}/terraform")

        assert response.status_code == 500
        assert "Terraform links" in response.json()["detail"]

    def test_get_terraform_links_partial_results(
        self, client, mock_resource_service, mock_graph_builder, sample_terraform_link
    ):
        """Test when graph returns links but some Terraform resources are missing."""
        # Graph returns 2 links
        mock_graph_builder.find_terraform_for_resource.return_value = [
            {"address": "azurerm_virtual_machine.test_vm"},
            {"address": "azurerm_virtual_machine.missing_vm"},
        ]

        # But only one exists in Cosmos DB
        async def mock_get_terraform(address):
            if address == "azurerm_virtual_machine.test_vm":
                return sample_terraform_link
            return None

        mock_resource_service.get_terraform_resource.side_effect = mock_get_terraform

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        response = client.get(f"/api/v1/resources{resource_id}/terraform")

        assert response.status_code == 200
        data = response.json()
        # Should only return the one that exists
        assert len(data) == 1


class TestGetResourceDependenciesEndpoint:
    """Tests for GET /resources/{resource_id}/dependencies endpoint."""

    def test_get_dependencies_success(self, client, mock_graph_builder):
        """Test successful dependency retrieval."""
        mock_graph_builder.find_dependencies.return_value = [
            {
                "id": "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet",
                "name": "test-vnet",
                "type": "Microsoft.Network/virtualNetworks",
                "relationship": "depends_on",
                "direction": "in",
            },
            {
                "id": "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Storage/storageAccounts/test-storage",
                "name": "test-storage",
                "type": "Microsoft.Storage/storageAccounts",
                "relationship": "uses",
                "direction": "out",
            },
        ]

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        response = client.get(f"/api/v1/resources{resource_id}/dependencies")

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert len(data) == 2
        assert data[0]["name"] == "test-vnet"
        assert data[0]["direction"] == "upstream"
        assert data[1]["name"] == "test-storage"
        assert data[1]["direction"] == "downstream"

    def test_get_dependencies_with_direction(self, client, mock_graph_builder):
        """Test dependency retrieval with direction filter."""
        mock_graph_builder.find_dependencies.return_value = []

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        # Test 'in' direction
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?direction=in")
        assert response.status_code == 200
        assert mock_graph_builder.find_dependencies.call_args[0][1] == "in"

        # Test 'out' direction
        mock_graph_builder.reset_mock()
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?direction=out")
        assert response.status_code == 200
        assert mock_graph_builder.find_dependencies.call_args[0][1] == "out"

        # Test 'both' direction (default)
        mock_graph_builder.reset_mock()
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?direction=both")
        assert response.status_code == 200
        assert mock_graph_builder.find_dependencies.call_args[0][1] == "both"

    def test_get_dependencies_with_depth(self, client, mock_graph_builder):
        """Test dependency retrieval with custom depth."""
        mock_graph_builder.find_dependencies.return_value = []

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        # Test depth 1
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?depth=1")
        assert response.status_code == 200
        assert mock_graph_builder.find_dependencies.call_args[0][2] == 1

        # Test depth 5
        mock_graph_builder.reset_mock()
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?depth=5")
        assert response.status_code == 200
        assert mock_graph_builder.find_dependencies.call_args[0][2] == 5

    def test_get_dependencies_validation_errors(self, client, mock_graph_builder):
        """Test validation errors for dependencies endpoint."""
        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        # Invalid direction
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?direction=invalid")
        assert response.status_code == 422

        # Depth too low
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?depth=0")
        assert response.status_code == 422

        # Depth too high
        response = client.get(f"/api/v1/resources{resource_id}/dependencies?depth=6")
        assert response.status_code == 422

    def test_get_dependencies_error(self, client, mock_graph_builder):
        """Test error handling for dependency retrieval."""
        mock_graph_builder.find_dependencies.side_effect = Exception("Graph error")

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        response = client.get(f"/api/v1/resources{resource_id}/dependencies")

        assert response.status_code == 500
        assert "dependencies" in response.json()["detail"].lower()


class TestResourceGraphQueryEndpoint:
    """Tests for POST /resources/resource-graph/query endpoint."""

    def test_query_success(self, client, mock_resource_service):
        """Test successful Resource Graph query."""
        mock_resource_service.execute_resource_graph_query.return_value = [
            {"name": "vm1", "type": "Microsoft.Compute/virtualMachines"},
            {"name": "vm2", "type": "Microsoft.Compute/virtualMachines"},
        ]

        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={
                "query": "Resources | where type == 'microsoft.compute/virtualmachines' | limit 10"
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert "results" in data
        assert "total_records" in data
        assert data["total_records"] == 2
        assert len(data["results"]) == 2

    def test_query_with_subscriptions(self, client, mock_resource_service):
        """Test query with subscription filter."""
        mock_resource_service.execute_resource_graph_query.return_value = []

        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={
                "query": "Resources | limit 10",
                "subscriptions": ["sub-1", "sub-2"],
            },
        )

        assert response.status_code == 200

        # Verify subscriptions were passed
        call_args = mock_resource_service.execute_resource_graph_query.call_args.kwargs
        assert call_args["subscriptions"] == ["sub-1", "sub-2"]

    def test_query_validation_missing_query(self, client, mock_resource_service):
        """Test validation when query is missing."""
        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={},
        )

        assert response.status_code == 422  # Validation error

    def test_query_validation_empty_query(self, client, mock_resource_service):
        """Test validation when query is empty."""
        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={"query": ""},
        )

        assert response.status_code == 422  # Validation error

    def test_query_validation_unsafe_semicolon(self, client, mock_resource_service):
        """Test that semicolons are blocked (injection protection)."""
        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={"query": "Resources | limit 10; DROP TABLE users"},
        )

        assert response.status_code == 400
        assert "unsafe" in response.json()["detail"].lower()

    def test_query_validation_unsafe_comment(self, client, mock_resource_service):
        """Test that SQL comments are blocked (injection protection)."""
        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={"query": "Resources | limit 10 -- comment"},
        )

        assert response.status_code == 400
        assert "unsafe" in response.json()["detail"].lower()

    def test_query_execution_error(self, client, mock_resource_service):
        """Test error handling for query execution failures."""
        mock_resource_service.execute_resource_graph_query.side_effect = Exception(
            "Query timeout"
        )

        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={"query": "Resources | limit 10"},
        )

        assert response.status_code == 500
        assert "Query execution failed" in response.json()["detail"]

    def test_query_too_long(self, client, mock_resource_service):
        """Test validation for overly long queries."""
        # Create a query > 10000 characters
        long_query = "Resources | where name == 'test'" + (" or name == 'x'" * 1000)

        response = client.post(
            "/api/v1/resources/resource-graph/query",
            json={"query": long_query},
        )

        assert response.status_code == 422  # Validation error


class TestResourceRouterIntegration:
    """Integration tests for resources router."""

    def test_full_resource_workflow(
        self, client, mock_resource_service, mock_graph_builder, sample_azure_resource, sample_terraform_link
    ):
        """Test a complete workflow: get resource, then get its Terraform code and dependencies."""
        # Setup mocks
        mock_resource_service.get_resource.return_value = sample_azure_resource
        mock_graph_builder.find_terraform_for_resource.return_value = [
            {"address": "azurerm_virtual_machine.test_vm"}
        ]
        mock_resource_service.get_terraform_resource.return_value = sample_terraform_link
        mock_graph_builder.find_dependencies.return_value = [
            {
                "id": "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet",
                "name": "test-vnet",
                "type": "Microsoft.Network/virtualNetworks",
                "relationship": "depends_on",
                "direction": "in",
            }
        ]

        resource_id = "/subscriptions/sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        # 1. Get resource details
        response1 = client.get(f"/api/v1/resources{resource_id}")
        assert response1.status_code == 200
        assert response1.json()["name"] == "test-vm"

        # 2. Get Terraform code
        response2 = client.get(f"/api/v1/resources{resource_id}/terraform")
        assert response2.status_code == 200
        assert len(response2.json()) == 1

        # 3. Get dependencies
        response3 = client.get(f"/api/v1/resources{resource_id}/dependencies")
        assert response3.status_code == 200
        assert len(response3.json()) == 1
