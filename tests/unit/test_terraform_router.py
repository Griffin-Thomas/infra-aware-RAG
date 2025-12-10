"""Unit tests for the Terraform API router."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.terraform import router
from src.api.dependencies import get_terraform_service
from src.api.models.terraform import (
    TerraformResource,
    TerraformPlan,
    PlannedChange,
    PlanAnalysis,
    ParsedPlan,
)


@pytest.fixture
def mock_terraform_service():
    """Create a mock Terraform service."""
    from unittest.mock import MagicMock
    mock = AsyncMock()
    # parse_plan is synchronous, not async
    mock.parse_plan = MagicMock()
    return mock


@pytest.fixture
def app(mock_terraform_service):
    """Create a test FastAPI app with the Terraform router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override the Terraform service dependency
    test_app.dependency_overrides[get_terraform_service] = lambda: mock_terraform_service

    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_terraform_resource():
    """Sample Terraform resource."""
    return TerraformResource(
        address="azurerm_virtual_machine.example",
        type="azurerm_virtual_machine",
        name="example",
        module_path=None,
        file_path="infrastructure/compute.tf",
        line_number=10,
        repo_url="https://github.com/org/repo",
        branch="main",
        provider="azurerm",
        source_code='resource "azurerm_virtual_machine" "example" {\n  name = "test-vm"\n}',
        dependencies=["azurerm_network_interface.example"],
        azure_resource_id="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/test-vm",
    )


@pytest.fixture
def sample_terraform_plan():
    """Sample Terraform plan."""
    return TerraformPlan(
        id="plan-123",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc123def456",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        add=5,
        change=3,
        destroy=1,
        changes=[
            PlannedChange(
                address="azurerm_virtual_machine.new_vm",
                action="create",
                resource_type="azurerm_virtual_machine",
                changed_attributes=[],
                summary="Create azurerm_virtual_machine resource",
            ),
            PlannedChange(
                address="azurerm_storage_account.storage",
                action="update",
                resource_type="azurerm_storage_account",
                changed_attributes=["account_tier", "tags"],
                summary="Update azurerm_storage_account resource (changing: account_tier, tags)",
            ),
        ],
    )


class TestListTerraformResources:
    """Tests for GET /terraform/resources endpoint."""

    def test_list_resources_no_filters(self, client, mock_terraform_service, sample_terraform_resource):
        """Test listing all Terraform resources."""
        mock_terraform_service.list_resources.return_value = [sample_terraform_resource]

        response = client.get("/api/v1/terraform/resources")

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert len(data) == 1
        assert data[0]["address"] == "azurerm_virtual_machine.example"
        assert data[0]["type"] == "azurerm_virtual_machine"
        assert data[0]["file_path"] == "infrastructure/compute.tf"

        # Verify service was called correctly
        mock_terraform_service.list_resources.assert_called_once()
        call_args = mock_terraform_service.list_resources.call_args.kwargs
        assert call_args["repo_url"] is None
        assert call_args["resource_type"] is None
        assert call_args["file_path"] is None
        assert call_args["limit"] == 50  # Default

    def test_list_resources_with_filters(self, client, mock_terraform_service, sample_terraform_resource):
        """Test listing resources with filters."""
        mock_terraform_service.list_resources.return_value = [sample_terraform_resource]

        response = client.get(
            "/api/v1/terraform/resources",
            params={
                "repo_url": "https://github.com/org/repo",
                "type": "azurerm_virtual_machine",
                "file_path": "infrastructure/compute.tf",
                "limit": 10,
            },
        )

        assert response.status_code == 200

        # Verify service was called with filters
        call_args = mock_terraform_service.list_resources.call_args.kwargs
        assert call_args["repo_url"] == "https://github.com/org/repo"
        assert call_args["resource_type"] == "azurerm_virtual_machine"
        assert call_args["file_path"] == "infrastructure/compute.tf"
        assert call_args["limit"] == 10

    def test_list_resources_validation_errors(self, client, mock_terraform_service):
        """Test validation errors for list resources."""
        # Limit too low
        response = client.get("/api/v1/terraform/resources?limit=0")
        assert response.status_code == 422

        # Limit too high
        response = client.get("/api/v1/terraform/resources?limit=201")
        assert response.status_code == 422

    def test_list_resources_empty(self, client, mock_terraform_service):
        """Test listing when no resources exist."""
        mock_terraform_service.list_resources.return_value = []

        response = client.get("/api/v1/terraform/resources")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_resources_error(self, client, mock_terraform_service):
        """Test error handling for list resources."""
        mock_terraform_service.list_resources.side_effect = Exception("Database error")

        response = client.get("/api/v1/terraform/resources")

        assert response.status_code == 500
        assert "Failed to list Terraform resources" in response.json()["detail"]


class TestGetTerraformResource:
    """Tests for GET /terraform/resources/{address} endpoint."""

    def test_get_resource_success(self, client, mock_terraform_service, sample_terraform_resource):
        """Test successful resource retrieval."""
        mock_terraform_service.get_resource.return_value = sample_terraform_resource

        response = client.get(
            "/api/v1/terraform/resources/azurerm_virtual_machine.example",
            params={"repo_url": "https://github.com/org/repo"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert data["address"] == "azurerm_virtual_machine.example"
        assert data["type"] == "azurerm_virtual_machine"
        assert data["provider"] == "azurerm"
        assert data["azure_resource_id"] is not None

        # Verify service was called correctly
        mock_terraform_service.get_resource.assert_called_once_with(
            "azurerm_virtual_machine.example",
            "https://github.com/org/repo",
        )

    def test_get_resource_not_found(self, client, mock_terraform_service):
        """Test resource not found."""
        mock_terraform_service.get_resource.return_value = None

        response = client.get(
            "/api/v1/terraform/resources/nonexistent",
            params={"repo_url": "https://github.com/org/repo"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_resource_missing_repo_url(self, client, mock_terraform_service):
        """Test missing required query parameter."""
        response = client.get("/api/v1/terraform/resources/azurerm_virtual_machine.example")

        assert response.status_code == 422  # Validation error

    def test_get_resource_with_module_path(self, client, mock_terraform_service):
        """Test getting resource with module in address."""
        resource = TerraformResource(
            address="module.networking.azurerm_virtual_network.main",
            type="azurerm_virtual_network",
            name="main",
            module_path="networking",
            file_path="modules/networking/main.tf",
            line_number=5,
            repo_url="https://github.com/org/repo",
            branch="main",
            provider="azurerm",
            source_code="resource block",
            dependencies=[],
            azure_resource_id=None,
        )

        mock_terraform_service.get_resource.return_value = resource

        response = client.get(
            "/api/v1/terraform/resources/module.networking.azurerm_virtual_network.main",
            params={"repo_url": "https://github.com/org/repo"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["module_path"] == "networking"


class TestListTerraformPlans:
    """Tests for GET /terraform/plans endpoint."""

    def test_list_plans_no_filters(self, client, mock_terraform_service, sample_terraform_plan):
        """Test listing all plans."""
        mock_terraform_service.list_plans.return_value = [sample_terraform_plan]

        response = client.get("/api/v1/terraform/plans")

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert len(data) == 1
        assert data[0]["id"] == "plan-123"
        assert data[0]["add"] == 5
        assert data[0]["change"] == 3
        assert data[0]["destroy"] == 1

        # Verify service was called
        mock_terraform_service.list_plans.assert_called_once()

    def test_list_plans_with_filters(self, client, mock_terraform_service, sample_terraform_plan):
        """Test listing plans with filters."""
        mock_terraform_service.list_plans.return_value = [sample_terraform_plan]

        since_date = "2024-01-01T00:00:00"
        response = client.get(
            "/api/v1/terraform/plans",
            params={
                "repo_url": "https://github.com/org/repo",
                "since": since_date,
                "limit": 5,
            },
        )

        assert response.status_code == 200

        # Verify service was called with filters
        call_args = mock_terraform_service.list_plans.call_args.kwargs
        assert call_args["repo_url"] == "https://github.com/org/repo"
        assert call_args["since"] is not None
        assert call_args["limit"] == 5

    def test_list_plans_validation(self, client, mock_terraform_service):
        """Test validation for list plans."""
        # Limit too low
        response = client.get("/api/v1/terraform/plans?limit=0")
        assert response.status_code == 422

        # Limit too high
        response = client.get("/api/v1/terraform/plans?limit=51")
        assert response.status_code == 422


class TestGetTerraformPlan:
    """Tests for GET /terraform/plans/{plan_id} endpoint."""

    def test_get_plan_success(self, client, mock_terraform_service, sample_terraform_plan):
        """Test successful plan retrieval."""
        mock_terraform_service.get_plan.return_value = sample_terraform_plan

        response = client.get("/api/v1/terraform/plans/plan-123")

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert data["id"] == "plan-123"
        assert data["commit_sha"] == "abc123def456"
        assert len(data["changes"]) == 2

    def test_get_plan_not_found(self, client, mock_terraform_service):
        """Test plan not found."""
        mock_terraform_service.get_plan.return_value = None

        response = client.get("/api/v1/terraform/plans/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestAnalyzeTerraformPlan:
    """Tests for POST /terraform/plans/{plan_id}/analyze endpoint."""

    def test_analyze_plan_success(self, client, mock_terraform_service, sample_terraform_plan):
        """Test successful plan analysis."""
        mock_terraform_service.get_plan.return_value = sample_terraform_plan
        mock_terraform_service.analyze_plan.return_value = PlanAnalysis(
            summary="Plan will add 5, change 3, and destroy 1 resources.",
            risk_level="medium",
            key_changes=["CREATE: azurerm_virtual_machine.new_vm"],
            recommendations=["Review all resources marked for destruction carefully"],
        )

        response = client.post("/api/v1/terraform/plans/plan-123/analyze")

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert data["risk_level"] == "medium"
        assert "add 5" in data["summary"]
        assert len(data["key_changes"]) > 0
        assert len(data["recommendations"]) > 0

        # Verify service was called
        mock_terraform_service.get_plan.assert_called_once_with("plan-123")
        mock_terraform_service.analyze_plan.assert_called_once()

    def test_analyze_plan_not_found(self, client, mock_terraform_service):
        """Test analyzing non-existent plan."""
        mock_terraform_service.get_plan.return_value = None

        response = client.post("/api/v1/terraform/plans/nonexistent/analyze")

        assert response.status_code == 404

    def test_analyze_plan_high_risk(self, client, mock_terraform_service, sample_terraform_plan):
        """Test analysis of high-risk plan."""
        # Create a plan with many destroys
        high_risk_plan = TerraformPlan(
            id="plan-456",
            repo_url="https://github.com/org/repo",
            branch="main",
            commit_sha="def456",
            timestamp=datetime.now(),
            add=0,
            change=0,
            destroy=10,
            changes=[],
        )

        mock_terraform_service.get_plan.return_value = high_risk_plan
        mock_terraform_service.analyze_plan.return_value = PlanAnalysis(
            summary="Plan will destroy 10 resources.",
            risk_level="high",
            key_changes=["DESTROY: multiple resources"],
            recommendations=["Review all resources marked for destruction carefully"],
        )

        response = client.post("/api/v1/terraform/plans/plan-456/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "high"


class TestParseTerraformPlan:
    """Tests for POST /terraform/plans/parse endpoint."""

    def test_parse_plan_success(self, client, mock_terraform_service):
        """Test successful plan parsing."""
        plan_json = {
            "resource_changes": [
                {
                    "address": "azurerm_virtual_machine.example",
                    "type": "azurerm_virtual_machine",
                    "change": {
                        "actions": ["create"],
                        "before": None,
                        "after": {"name": "test-vm"},
                    },
                }
            ]
        }

        mock_terraform_service.parse_plan.return_value = ParsedPlan(
            add=1,
            change=0,
            destroy=0,
            changes=[
                PlannedChange(
                    address="azurerm_virtual_machine.example",
                    action="create",
                    resource_type="azurerm_virtual_machine",
                    changed_attributes=[],
                    summary="Create azurerm_virtual_machine resource",
                )
            ],
        )

        response = client.post("/api/v1/terraform/plans/parse", json=plan_json)

        assert response.status_code == 200
        data = response.json()

        # Verify response
        assert data["add"] == 1
        assert data["change"] == 0
        assert data["destroy"] == 0
        assert len(data["changes"]) == 1

        # Verify service was called
        mock_terraform_service.parse_plan.assert_called_once_with(plan_json)

    def test_parse_plan_invalid_json(self, client, mock_terraform_service):
        """Test parsing invalid plan JSON."""
        mock_terraform_service.parse_plan.side_effect = ValueError("Invalid plan JSON")

        response = client.post("/api/v1/terraform/plans/parse", json={"invalid": "data"})

        assert response.status_code == 400
        assert "Invalid" in response.json()["detail"]

    def test_parse_plan_complex(self, client, mock_terraform_service):
        """Test parsing complex plan with multiple actions."""
        plan_json = {
            "resource_changes": [
                {
                    "address": "azurerm_virtual_machine.vm1",
                    "type": "azurerm_virtual_machine",
                    "change": {"actions": ["create"]},
                },
                {
                    "address": "azurerm_storage_account.storage",
                    "type": "azurerm_storage_account",
                    "change": {"actions": ["update"]},
                },
                {
                    "address": "azurerm_network_interface.old_nic",
                    "type": "azurerm_network_interface",
                    "change": {"actions": ["delete"]},
                },
            ]
        }

        mock_terraform_service.parse_plan.return_value = ParsedPlan(
            add=1,
            change=1,
            destroy=1,
            changes=[
                PlannedChange(
                    address="azurerm_virtual_machine.vm1",
                    action="create",
                    resource_type="azurerm_virtual_machine",
                    changed_attributes=[],
                    summary="Create azurerm_virtual_machine resource",
                ),
                PlannedChange(
                    address="azurerm_storage_account.storage",
                    action="update",
                    resource_type="azurerm_storage_account",
                    changed_attributes=["account_tier"],
                    summary="Update azurerm_storage_account resource (changing: account_tier)",
                ),
                PlannedChange(
                    address="azurerm_network_interface.old_nic",
                    action="delete",
                    resource_type="azurerm_network_interface",
                    changed_attributes=[],
                    summary="Delete azurerm_network_interface resource",
                ),
            ],
        )

        response = client.post("/api/v1/terraform/plans/parse", json=plan_json)

        assert response.status_code == 200
        data = response.json()

        assert data["add"] == 1
        assert data["change"] == 1
        assert data["destroy"] == 1
        assert len(data["changes"]) == 3


class TestTerraformRouterIntegration:
    """Integration tests for Terraform router."""

    def test_full_terraform_workflow(
        self, client, mock_terraform_service, sample_terraform_resource, sample_terraform_plan
    ):
        """Test complete workflow: list resources, get plan, analyze."""
        # Setup mocks
        mock_terraform_service.list_resources.return_value = [sample_terraform_resource]
        mock_terraform_service.get_plan.return_value = sample_terraform_plan
        mock_terraform_service.analyze_plan.return_value = PlanAnalysis(
            summary="Test summary",
            risk_level="low",
            key_changes=["CREATE: test"],
            recommendations=["Test recommendation"],
        )

        # 1. List resources
        response1 = client.get("/api/v1/terraform/resources")
        assert response1.status_code == 200
        assert len(response1.json()) == 1

        # 2. Get plan
        response2 = client.get("/api/v1/terraform/plans/plan-123")
        assert response2.status_code == 200
        assert response2.json()["id"] == "plan-123"

        # 3. Analyze plan
        response3 = client.post("/api/v1/terraform/plans/plan-123/analyze")
        assert response3.status_code == 200
        assert response3.json()["risk_level"] == "low"
