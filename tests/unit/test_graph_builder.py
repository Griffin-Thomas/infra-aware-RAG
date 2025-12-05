"""Unit tests for graph builder."""

from unittest.mock import Mock, call, patch

import pytest

from src.indexing.graph_builder import GraphBuilder


@pytest.fixture
def mock_gremlin_client():
    """Create mock Gremlin client."""
    mock_client = Mock()
    mock_client.submit = Mock(return_value=[])
    mock_client.close = Mock()
    return mock_client


@pytest.fixture
def graph_builder(mock_gremlin_client):
    """Create test graph builder."""
    with patch("src.indexing.graph_builder.client.Client", return_value=mock_gremlin_client):
        builder = GraphBuilder(
            endpoint="https://test.documents.azure.com:443/",
            database="test-db",
            graph="test-graph",
            key="test-key",
        )
        yield builder


class TestGraphBuilder:
    """Test suite for GraphBuilder."""

    def test_init(self, mock_gremlin_client):
        """Test graph builder initialization."""
        with patch("src.indexing.graph_builder.client.Client", return_value=mock_gremlin_client) as mock_client_class:
            builder = GraphBuilder(
                endpoint="https://myaccount.documents.azure.com:443/",
                database="infra-db",
                graph="infra-graph",
                key="test-key-123",
            )

            assert builder.endpoint == "https://myaccount.documents.azure.com:443/"
            assert builder.database == "infra-db"
            assert builder.graph == "infra-graph"

            # Check that Gremlin endpoint was constructed correctly
            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args
            assert "wss://myaccount.gremlin.cosmos.azure.com:443/" in call_args[0][0]
            assert call_args[1]["username"] == "/dbs/infra-db/colls/infra-graph"

    def test_add_subscription(self, graph_builder, mock_gremlin_client):
        """Test adding a subscription vertex."""
        graph_builder.add_subscription(
            sub_id="sub-123",
            name="Production",
            tenant_id="tenant-456",
        )

        mock_gremlin_client.submit.assert_called_once()
        call_args = mock_gremlin_client.submit.call_args

        # Check query contains key Gremlin operations
        query = call_args[0][0]
        assert "subscription" in query
        assert "addV" in query
        assert "coalesce" in query

        # Check bindings
        bindings = call_args[0][1]
        assert bindings["sub_id"] == "sub-123"
        assert bindings["name"] == "Production"
        assert bindings["tenant_id"] == "tenant-456"

    def test_add_resource_group(self, graph_builder, mock_gremlin_client):
        """Test adding a resource group vertex with subscription edge."""
        graph_builder.add_resource_group(
            rg_id="/subscriptions/sub-123/resourceGroups/rg-prod",
            name="rg-prod",
            sub_id="sub-123",
            location="canadaeast",
        )

        # Should make 2 calls: vertex + edge
        assert mock_gremlin_client.submit.call_count == 2

        # Check first call (vertex)
        first_call = mock_gremlin_client.submit.call_args_list[0]
        query = first_call[0][0]
        assert "resource_group" in query
        assert "addV" in query

        bindings = first_call[0][1]
        assert bindings["rg_id"] == "/subscriptions/sub-123/resourceGroups/rg-prod"
        assert bindings["name"] == "rg-prod"
        assert bindings["location"] == "canadaeast"

        # Check second call (edge)
        second_call = mock_gremlin_client.submit.call_args_list[1]
        query = second_call[0][0]
        assert "contains" in query
        assert "addE" in query

    def test_add_azure_resource(self, graph_builder, mock_gremlin_client):
        """Test adding an Azure resource vertex."""
        resource = {
            "id": "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "name": "vm-1",
            "location": "canadaeast",
            "subscription_id": "sub-123",
            "resource_group": "rg-prod",
        }

        graph_builder.add_azure_resource(resource)

        # Should make 2 calls: vertex + edge
        assert mock_gremlin_client.submit.call_count == 2

        # Check first call (vertex)
        first_call = mock_gremlin_client.submit.call_args_list[0]
        query = first_call[0][0]
        assert "azure_resource" in query
        assert "addV" in query

        bindings = first_call[0][1]
        assert bindings["res_id"] == resource["id"]
        assert bindings["res_type"] == "Microsoft.Compute/virtualMachines"
        assert bindings["name"] == "vm-1"

    def test_add_resource_dependency(self, graph_builder, mock_gremlin_client):
        """Test adding a dependency edge between resources."""
        graph_builder.add_resource_dependency(
            from_id="/subscriptions/sub-123/.../vm-1",
            to_id="/subscriptions/sub-123/.../vnet-1",
            dep_type="depends_on",
        )

        mock_gremlin_client.submit.assert_called_once()
        call_args = mock_gremlin_client.submit.call_args

        query = call_args[0][0]
        assert "addE" in query

        bindings = call_args[0][1]
        assert bindings["from_id"] == "/subscriptions/sub-123/.../vm-1"
        assert bindings["to_id"] == "/subscriptions/sub-123/.../vnet-1"
        assert bindings["dep_type"] == "depends_on"

    def test_add_terraform_resource(self, graph_builder, mock_gremlin_client):
        """Test adding a Terraform resource vertex."""
        tf_resource = {
            "address": "azurerm_resource_group.main",
            "type": "azurerm_resource_group",
            "file_path": "main.tf",
            "repo_url": "https://github.com/user/repo.git",
            "branch": "main",
        }

        graph_builder.add_terraform_resource(tf_resource)

        mock_gremlin_client.submit.assert_called_once()
        call_args = mock_gremlin_client.submit.call_args

        query = call_args[0][0]
        assert "terraform_resource" in query
        assert "addV" in query

        bindings = call_args[0][1]
        assert bindings["tf_addr"] == "azurerm_resource_group.main"
        assert bindings["tf_type"] == "azurerm_resource_group"
        assert bindings["file_path"] == "main.tf"

    def test_link_terraform_to_azure(self, graph_builder, mock_gremlin_client):
        """Test linking Terraform resource to Azure resource."""
        graph_builder.link_terraform_to_azure(
            tf_address="azurerm_resource_group.main",
            azure_id="/subscriptions/sub-123/resourceGroups/rg-prod",
        )

        mock_gremlin_client.submit.assert_called_once()
        call_args = mock_gremlin_client.submit.call_args

        query = call_args[0][0]
        assert "manages" in query
        assert "addE" in query

        bindings = call_args[0][1]
        assert bindings["tf_addr"] == "azurerm_resource_group.main"
        assert bindings["azure_id"] == "/subscriptions/sub-123/resourceGroups/rg-prod"

    def test_find_dependencies_both_directions(self, graph_builder, mock_gremlin_client):
        """Test finding dependencies in both directions."""
        mock_gremlin_client.submit = Mock(return_value=[{"path": ["resource1", "resource2"]}])

        results = graph_builder.find_dependencies(
            resource_id="/subscriptions/sub-123/.../vm-1",
            direction="both",
            depth=2,
        )

        assert len(results) == 1
        mock_gremlin_client.submit.assert_called_once()

        call_args = mock_gremlin_client.submit.call_args
        query = call_args[0][0]
        assert "bothE" in query
        assert "times(2)" in query

    def test_find_dependencies_in_direction(self, graph_builder, mock_gremlin_client):
        """Test finding incoming dependencies (dependents)."""
        mock_gremlin_client.submit = Mock(return_value=[])

        results = graph_builder.find_dependencies(
            resource_id="/subscriptions/sub-123/.../vm-1",
            direction="in",
            depth=3,
        )

        call_args = mock_gremlin_client.submit.call_args
        query = call_args[0][0]
        assert "inE" in query
        assert "times(3)" in query

    def test_find_dependencies_out_direction(self, graph_builder, mock_gremlin_client):
        """Test finding outgoing dependencies."""
        mock_gremlin_client.submit = Mock(return_value=[])

        results = graph_builder.find_dependencies(
            resource_id="/subscriptions/sub-123/.../vm-1",
            direction="out",
            depth=1,
        )

        call_args = mock_gremlin_client.submit.call_args
        query = call_args[0][0]
        assert "outE" in query
        assert "times(1)" in query

    def test_find_terraform_for_resource(self, graph_builder, mock_gremlin_client):
        """Test finding Terraform resources that manage an Azure resource."""
        mock_results = [
            {
                "address": "azurerm_resource_group.main",
                "file_path": "main.tf",
                "repo_url": "https://github.com/user/repo.git",
                "branch": "main",
            }
        ]
        mock_gremlin_client.submit = Mock(return_value=mock_results)

        results = graph_builder.find_terraform_for_resource(
            azure_id="/subscriptions/sub-123/resourceGroups/rg-prod"
        )

        assert len(results) == 1
        assert results[0]["address"] == "azurerm_resource_group.main"
        assert results[0]["file_path"] == "main.tf"

        call_args = mock_gremlin_client.submit.call_args
        query = call_args[0][0]
        assert "manages" in query
        assert "inE" in query
        assert "project" in query

    def test_find_resource_group_resources(self, graph_builder, mock_gremlin_client):
        """Test finding all resources in a resource group."""
        mock_results = [
            {
                "id": "/subscriptions/sub-123/.../vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "name": "vm-1",
                "location": "canadaeast",
            },
            {
                "id": "/subscriptions/sub-123/.../vnet-1",
                "type": "Microsoft.Network/virtualNetworks",
                "name": "vnet-1",
                "location": "canadaeast",
            },
        ]
        mock_gremlin_client.submit = Mock(return_value=mock_results)

        results = graph_builder.find_resource_group_resources(
            rg_id="/subscriptions/sub-123/resourceGroups/rg-prod"
        )

        assert len(results) == 2
        assert results[0]["type"] == "Microsoft.Compute/virtualMachines"
        assert results[1]["type"] == "Microsoft.Network/virtualNetworks"

        call_args = mock_gremlin_client.submit.call_args
        query = call_args[0][0]
        assert "resource_group" in query
        assert "contains" in query
        assert "azure_resource" in query

    def test_clear_graph(self, graph_builder, mock_gremlin_client):
        """Test clearing all data from graph."""
        graph_builder.clear_graph()

        mock_gremlin_client.submit.assert_called_once()
        call_args = mock_gremlin_client.submit.call_args

        query = call_args[0][0]
        assert "g.V().drop()" in query

    def test_close(self, graph_builder, mock_gremlin_client):
        """Test closing the graph builder."""
        graph_builder.close()

        mock_gremlin_client.close.assert_called_once()

    def test_add_subscription_error(self, graph_builder, mock_gremlin_client):
        """Test error handling when adding subscription."""
        mock_gremlin_client.submit = Mock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception, match="Connection failed"):
            graph_builder.add_subscription(
                sub_id="sub-123",
                name="Production",
                tenant_id="tenant-456",
            )

    def test_add_resource_group_error(self, graph_builder, mock_gremlin_client):
        """Test error handling when adding resource group."""
        mock_gremlin_client.submit = Mock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception, match="Connection failed"):
            graph_builder.add_resource_group(
                rg_id="/subscriptions/sub-123/resourceGroups/rg-prod",
                name="rg-prod",
                sub_id="sub-123",
                location="canadaeast",
            )

    def test_find_dependencies_error(self, graph_builder, mock_gremlin_client):
        """Test error handling when finding dependencies."""
        mock_gremlin_client.submit = Mock(side_effect=Exception("Query failed"))

        with pytest.raises(Exception, match="Query failed"):
            graph_builder.find_dependencies(
                resource_id="/subscriptions/sub-123/.../vm-1"
            )

    def test_endpoint_conversion(self, mock_gremlin_client):
        """Test that Cosmos DB endpoint is correctly converted to Gremlin endpoint."""
        with patch("src.indexing.graph_builder.client.Client", return_value=mock_gremlin_client) as mock_client_class:
            GraphBuilder(
                endpoint="https://myaccount.documents.azure.com:443/",
                database="test-db",
                graph="test-graph",
                key="test-key",
            )

            call_args = mock_client_class.call_args
            gremlin_endpoint = call_args[0][0]

            assert gremlin_endpoint.startswith("wss://")
            assert "gremlin.cosmos.azure.com" in gremlin_endpoint
            assert ".documents.azure.com" not in gremlin_endpoint
