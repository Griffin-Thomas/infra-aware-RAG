"""Integration tests for Cosmos DB Gremlin graph builder.

These tests require actual Cosmos DB with Gremlin API and will be skipped unless
the AZURE_INTEGRATION_TESTS environment variable is set.

Prerequisites:
- Azure CLI logged in (az login) OR
- Environment variables set:
  - COSMOS_DB_ENDPOINT (required)
  - COSMOS_DB_KEY (required)
  - COSMOS_DB_DATABASE (optional, defaults to 'infra-db')
  - COSMOS_DB_GRAPH (optional, defaults to 'infra-graph')
- Cosmos DB Gremlin API account deployed in Canada East or Canada Central
"""

import os

import pytest

from src.indexing.graph_builder import GraphBuilder

# Skip all tests unless integration tests are enabled
pytestmark = pytest.mark.skipif(
    not os.getenv("AZURE_INTEGRATION_TESTS"),
    reason="Integration tests disabled. Set AZURE_INTEGRATION_TESTS=1 to enable.",
)


@pytest.fixture
def cosmos_config():
    """Get Cosmos DB configuration from environment."""
    endpoint = os.getenv("COSMOS_DB_ENDPOINT")
    key = os.getenv("COSMOS_DB_KEY")
    database = os.getenv("COSMOS_DB_DATABASE", "infra-db")
    graph = os.getenv("COSMOS_DB_GRAPH", "infra-graph")

    if not endpoint or not key:
        pytest.skip("COSMOS_DB_ENDPOINT and COSMOS_DB_KEY must be set")

    return {
        "endpoint": endpoint,
        "key": key,
        "database": database,
        "graph": graph,
    }


@pytest.fixture
def graph_builder(cosmos_config):
    """Create GraphBuilder instance for testing."""
    builder = GraphBuilder(
        endpoint=cosmos_config["endpoint"],
        database=cosmos_config["database"],
        graph=cosmos_config["graph"],
        key=cosmos_config["key"],
    )
    yield builder
    builder.close()


@pytest.mark.integration
def test_add_subscription(graph_builder):
    """Test adding a subscription vertex."""
    # Add subscription
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    print("Successfully added subscription vertex")


@pytest.mark.integration
def test_add_resource_group(graph_builder):
    """Test adding a resource group vertex with subscription edge."""
    # Add subscription first
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    # Add resource group
    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    print("Successfully added resource group vertex with subscription edge")


@pytest.mark.integration
def test_add_azure_resource(graph_builder):
    """Test adding an Azure resource vertex with edges."""
    # Add subscription
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    # Add resource group
    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    # Add Azure resource
    resource = {
        "id": "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        "type": "Microsoft.Compute/virtualMachines",
        "name": "test-vm",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    }

    graph_builder.add_azure_resource(resource)

    print(f"Successfully added Azure resource: {resource['name']}")


@pytest.mark.integration
def test_add_resource_dependency(graph_builder):
    """Test adding a dependency edge between resources."""
    # Add subscription
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    # Add resource group
    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    # Add two resources
    vm_resource = {
        "id": "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        "type": "Microsoft.Compute/virtualMachines",
        "name": "test-vm",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    }

    vnet_resource = {
        "id": "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet",
        "type": "Microsoft.Network/virtualNetworks",
        "name": "test-vnet",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    }

    graph_builder.add_azure_resource(vm_resource)
    graph_builder.add_azure_resource(vnet_resource)

    # Add dependency (VM depends on VNet)
    graph_builder.add_resource_dependency(
        from_id=vm_resource["id"],
        to_id=vnet_resource["id"],
        dep_type="depends_on",
    )

    print("Successfully added resource dependency edge")


@pytest.mark.integration
def test_add_terraform_resource(graph_builder):
    """Test adding a Terraform resource vertex."""
    # Add Terraform resource
    graph_builder.add_terraform_resource(
        address="azurerm_virtual_machine.test",
        resource_type="azurerm_virtual_machine",
        file_path="main.tf",
        repo_url="https://github.com/test/repo",
    )

    print("Successfully added Terraform resource vertex")


@pytest.mark.integration
def test_link_terraform_to_azure(graph_builder):
    """Test linking Terraform resource to Azure resource."""
    # Add subscription
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    # Add resource group
    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    # Add Azure resource
    azure_resource = {
        "id": "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        "type": "Microsoft.Compute/virtualMachines",
        "name": "test-vm",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    }
    graph_builder.add_azure_resource(azure_resource)

    # Add Terraform resource
    graph_builder.add_terraform_resource(
        address="azurerm_virtual_machine.test",
        resource_type="azurerm_virtual_machine",
        file_path="main.tf",
        repo_url="https://github.com/test/repo",
    )

    # Link them
    graph_builder.link_terraform_to_azure(
        tf_address="azurerm_virtual_machine.test",
        azure_resource_id=azure_resource["id"],
    )

    print("Successfully linked Terraform resource to Azure resource")


@pytest.mark.integration
def test_find_dependencies_both_directions(graph_builder):
    """Test finding dependencies in both directions."""
    # Build a small graph
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    vm_id = "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
    vnet_id = "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet"

    graph_builder.add_azure_resource({
        "id": vm_id,
        "type": "Microsoft.Compute/virtualMachines",
        "name": "test-vm",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    })

    graph_builder.add_azure_resource({
        "id": vnet_id,
        "type": "Microsoft.Network/virtualNetworks",
        "name": "test-vnet",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    })

    graph_builder.add_resource_dependency(vm_id, vnet_id)

    # Find dependencies
    deps = graph_builder.find_dependencies(
        resource_id=vm_id,
        direction="both",
        depth=2,
    )

    print(f"Found {len(deps)} dependency paths from VM")
    assert len(deps) > 0, "Expected to find at least one dependency path"


@pytest.mark.integration
def test_find_dependencies_outgoing_only(graph_builder):
    """Test finding outgoing dependencies only."""
    # Build graph
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    vm_id = "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm-2"
    vnet_id = "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet-2"

    graph_builder.add_azure_resource({
        "id": vm_id,
        "type": "Microsoft.Compute/virtualMachines",
        "name": "test-vm-2",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    })

    graph_builder.add_azure_resource({
        "id": vnet_id,
        "type": "Microsoft.Network/virtualNetworks",
        "name": "test-vnet-2",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    })

    graph_builder.add_resource_dependency(vm_id, vnet_id)

    # Find outgoing dependencies
    deps = graph_builder.find_dependencies(
        resource_id=vm_id,
        direction="out",
        depth=1,
    )

    print(f"Found {len(deps)} outgoing dependency paths")


@pytest.mark.integration
def test_find_terraform_for_resource(graph_builder):
    """Test finding Terraform resources linked to an Azure resource."""
    # Build graph with Terraform linkage
    graph_builder.add_subscription(
        sub_id="test-sub-123",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-123/resourceGroups/test-rg",
        name="test-rg",
        sub_id="test-sub-123",
        location="canadaeast",
    )

    azure_id = "/subscriptions/test-sub-123/resourceGroups/test-rg/providers/Microsoft.Storage/storageAccounts/teststorage"

    graph_builder.add_azure_resource({
        "id": azure_id,
        "type": "Microsoft.Storage/storageAccounts",
        "name": "teststorage",
        "location": "canadaeast",
        "subscription_id": "test-sub-123",
        "resource_group": "test-rg",
    })

    graph_builder.add_terraform_resource(
        address="azurerm_storage_account.test",
        resource_type="azurerm_storage_account",
        file_path="storage.tf",
        repo_url="https://github.com/test/repo",
    )

    graph_builder.link_terraform_to_azure(
        tf_address="azurerm_storage_account.test",
        azure_resource_id=azure_id,
    )

    # Find Terraform resources
    tf_resources = graph_builder.find_terraform_for_resource(azure_id)

    print(f"Found {len(tf_resources)} Terraform resources for Azure resource")
    assert len(tf_resources) > 0, "Expected to find linked Terraform resource"


@pytest.mark.integration
def test_idempotent_vertex_creation(graph_builder):
    """Test that adding the same vertex multiple times is idempotent."""
    # Add subscription twice
    graph_builder.add_subscription(
        sub_id="test-sub-idempotent",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    graph_builder.add_subscription(
        sub_id="test-sub-idempotent",
        name="Test Subscription Updated",  # Updated name
        tenant_id="test-tenant-456",
    )

    print("Idempotent vertex creation successful (no errors)")


@pytest.mark.integration
def test_idempotent_edge_creation(graph_builder):
    """Test that adding the same edge multiple times is idempotent."""
    # Create graph
    graph_builder.add_subscription(
        sub_id="test-sub-edge",
        name="Test Subscription",
        tenant_id="test-tenant-456",
    )

    # Add resource group twice (which creates edge to subscription)
    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-edge/resourceGroups/test-rg-edge",
        name="test-rg-edge",
        sub_id="test-sub-edge",
        location="canadaeast",
    )

    graph_builder.add_resource_group(
        rg_id="/subscriptions/test-sub-edge/resourceGroups/test-rg-edge",
        name="test-rg-edge",
        sub_id="test-sub-edge",
        location="canadaeast",
    )

    print("Idempotent edge creation successful (no errors)")


@pytest.mark.integration
@pytest.mark.slow
def test_complex_graph_traversal(graph_builder):
    """Test traversing a more complex graph with multiple levels."""
    # Build a 3-level hierarchy
    sub_id = "test-sub-complex"
    rg_id = f"/subscriptions/{sub_id}/resourceGroups/test-rg-complex"
    vnet_id = f"{rg_id}/providers/Microsoft.Network/virtualNetworks/test-vnet-complex"
    subnet_id = f"{vnet_id}/subnets/test-subnet"
    vm_id = f"{rg_id}/providers/Microsoft.Compute/virtualMachines/test-vm-complex"

    # Add all vertices
    graph_builder.add_subscription(sub_id, "Complex Test Subscription", "test-tenant")
    graph_builder.add_resource_group(rg_id, "test-rg-complex", sub_id, "canadaeast")

    graph_builder.add_azure_resource({
        "id": vnet_id,
        "type": "Microsoft.Network/virtualNetworks",
        "name": "test-vnet-complex",
        "location": "canadaeast",
        "subscription_id": sub_id,
        "resource_group": "test-rg-complex",
    })

    graph_builder.add_azure_resource({
        "id": subnet_id,
        "type": "Microsoft.Network/virtualNetworks/subnets",
        "name": "test-subnet",
        "location": "canadaeast",
        "subscription_id": sub_id,
        "resource_group": "test-rg-complex",
    })

    graph_builder.add_azure_resource({
        "id": vm_id,
        "type": "Microsoft.Compute/virtualMachines",
        "name": "test-vm-complex",
        "location": "canadaeast",
        "subscription_id": sub_id,
        "resource_group": "test-rg-complex",
    })

    # Add dependencies
    graph_builder.add_resource_dependency(subnet_id, vnet_id)  # Subnet depends on VNet
    graph_builder.add_resource_dependency(vm_id, subnet_id)    # VM depends on Subnet

    # Traverse from VM with depth 3
    paths = graph_builder.find_dependencies(vm_id, direction="both", depth=3)

    print(f"Complex graph traversal found {len(paths)} paths")
    assert len(paths) > 0, "Expected to find paths in complex graph"
