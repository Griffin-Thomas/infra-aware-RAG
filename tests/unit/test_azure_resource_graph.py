"""Unit tests for Azure Resource Graph connector."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.exceptions import AzureError

from src.ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector


@pytest.fixture
def mock_credential():
    """Mock Azure credential."""
    credential = AsyncMock()
    credential.close = AsyncMock()
    return credential


@pytest.fixture
def connector(mock_credential):
    """Create a connector instance with mocked credential."""
    return AzureResourceGraphConnector(
        subscription_ids=["sub-123", "sub-456"], credential=mock_credential, page_size=100
    )


@pytest.fixture
def sample_resource():
    """Sample resource data from Resource Graph."""
    return {
        "id": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-test",
        "name": "vm-test",
        "type": "Microsoft.Compute/virtualMachines",
        "resourceGroup": "rg-test",
        "subscriptionId": "sub-123",
        "location": "canadaeast",
        "tags": {"Environment": "Test", "Owner": "TeamA"},
        "sku": {"name": "Standard_D2s_v3"},
        "kind": None,
        "managedBy": None,
        "properties": {"vmId": "abc-123", "provisioningState": "Succeeded"},
        "createdTime": "2024-01-15T10:00:00Z",
        "changedTime": "2024-01-20T15:30:00Z",
    }


class TestAzureResourceGraphConnector:
    """Test suite for AzureResourceGraphConnector."""

    @pytest.mark.asyncio
    async def test_init_with_defaults(self):
        """Test connector initialization with default values."""
        connector = AzureResourceGraphConnector()
        assert connector.subscription_ids == []
        assert connector.page_size == 1000
        assert connector.max_retries == 3
        assert connector.credential is not None

    @pytest.mark.asyncio
    async def test_init_with_custom_values(self, mock_credential):
        """Test connector initialization with custom values."""
        connector = AzureResourceGraphConnector(
            subscription_ids=["sub-1", "sub-2"],
            credential=mock_credential,
            page_size=500,
            max_retries=5,
        )
        assert connector.subscription_ids == ["sub-1", "sub-2"]
        assert connector.page_size == 500
        assert connector.max_retries == 5
        assert connector.credential == mock_credential

    @pytest.mark.asyncio
    async def test_page_size_capped_at_1000(self, mock_credential):
        """Test that page size is capped at Azure's maximum of 1000."""
        connector = AzureResourceGraphConnector(
            credential=mock_credential, page_size=5000  # Too large
        )
        assert connector.page_size == 1000

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_credential):
        """Test async context manager."""
        connector = AzureResourceGraphConnector(credential=mock_credential)

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                assert connector._client is not None

            # Verify cleanup
            mock_client.close.assert_called_once()
            mock_credential.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_all_resources_single_page(self, connector, sample_resource):
        """Test fetching resources with a single page of results."""
        mock_response = MagicMock()
        mock_response.data = [sample_resource]
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                resources = []
                async for resource in connector.fetch_all_resources():
                    resources.append(resource)

                assert len(resources) == 1
                assert resources[0] == sample_resource
                mock_client.resources.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_all_resources_multiple_pages(self, connector, sample_resource):
        """Test fetching resources with pagination."""
        # Create two pages of results
        mock_response_1 = MagicMock()
        mock_response_1.data = [sample_resource]
        mock_response_1.skip_token = "page2_token"

        mock_response_2 = MagicMock()
        mock_response_2.data = [sample_resource]
        mock_response_2.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(side_effect=[mock_response_1, mock_response_2])
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                resources = []
                async for resource in connector.fetch_all_resources():
                    resources.append(resource)

                assert len(resources) == 2
                assert mock_client.resources.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_all_resources_with_resource_types(self, connector, sample_resource):
        """Test fetching resources filtered by resource type."""
        mock_response = MagicMock()
        mock_response.data = [sample_resource]
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                resources = []
                async for resource in connector.fetch_all_resources(
                    resource_types=["Microsoft.Compute/virtualMachines"]
                ):
                    resources.append(resource)

                # Verify the query was modified to include type filter
                call_args = mock_client.resources.call_args[0][0]
                assert "where" in call_args.query
                assert "Microsoft.Compute/virtualMachines" in call_args.query

    @pytest.mark.asyncio
    async def test_fetch_resource_by_id(self, connector, sample_resource):
        """Test fetching a single resource by ID."""
        mock_response = MagicMock()
        mock_response.data = [sample_resource]
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                resource = await connector.fetch_resource_by_id(sample_resource["id"])

                assert resource is not None
                assert resource == sample_resource

    @pytest.mark.asyncio
    async def test_fetch_resource_by_id_not_found(self, connector):
        """Test fetching a non-existent resource."""
        mock_response = MagicMock()
        mock_response.data = []
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                resource = await connector.fetch_resource_by_id("/invalid/resource/id")
                assert resource is None

    @pytest.mark.asyncio
    async def test_fetch_resource_types(self, connector):
        """Test fetching resource type summary."""
        mock_response = MagicMock()
        mock_response.data = [
            {"type": "Microsoft.Compute/virtualMachines", "count_": 10},
            {"type": "Microsoft.Network/virtualNetworks", "count_": 5},
        ]
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                types = await connector.fetch_resource_types()

                assert len(types) == 2
                assert types[0]["type"] == "Microsoft.Compute/virtualMachines"
                assert types[0]["count_"] == 10

    @pytest.mark.asyncio
    async def test_enumerate_subscriptions(self, connector):
        """Test enumerating subscriptions."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "subscriptionId": "sub-123",
                "name": "Test Subscription 1",
                "properties": {"state": "Enabled"},
            },
            {
                "subscriptionId": "sub-456",
                "name": "Test Subscription 2",
                "properties": {"state": "Enabled"},
            },
        ]
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                subscriptions = await connector.enumerate_subscriptions()

                assert len(subscriptions) == 2
                assert subscriptions[0]["id"] == "sub-123"
                assert subscriptions[0]["name"] == "Test Subscription 1"
                assert subscriptions[0]["state"] == "Enabled"

    @pytest.mark.asyncio
    async def test_retry_on_azure_error(self, connector, sample_resource):
        """Test retry logic on Azure errors."""
        mock_response = MagicMock()
        mock_response.data = [sample_resource]
        mock_response.skip_token = None

        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            # Fail twice, then succeed
            mock_client.resources = AsyncMock(
                side_effect=[AzureError("Throttled"), AzureError("Throttled"), mock_response]
            )
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                resources = []
                async for resource in connector.fetch_all_resources():
                    resources.append(resource)

                assert len(resources) == 1
                assert mock_client.resources.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, connector):
        """Test that errors are raised after max retries."""
        with patch(
            "src.ingestion.connectors.azure_resource_graph.ResourceGraphClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.resources = AsyncMock(side_effect=AzureError("Persistent error"))
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            async with connector:
                with pytest.raises(AzureError):
                    async for _ in connector.fetch_all_resources():
                        pass

    def test_convert_to_document(self, connector, sample_resource):
        """Test converting raw resource to document."""
        doc = connector.convert_to_document(sample_resource, subscription_name="Test Sub")

        assert doc.id == sample_resource["id"]
        assert doc.name == "vm-test"
        assert doc.type == "Microsoft.Compute/virtualMachines"
        assert doc.resource_group == "rg-test"
        assert doc.subscription_id == "sub-123"
        assert doc.subscription_name == "Test Sub"
        assert doc.location == "canadaeast"
        assert doc.tags == {"Environment": "Test", "Owner": "TeamA"}
        assert doc.sku == {"name": "Standard_D2s_v3"}
        assert doc.searchable_text != ""

    def test_convert_to_document_without_subscription_name(self, connector, sample_resource):
        """Test document conversion falls back to subscription ID."""
        doc = connector.convert_to_document(sample_resource)

        assert doc.subscription_name == "sub-123"  # Falls back to subscription ID

    @pytest.mark.asyncio
    async def test_fetch_without_context_manager_raises(self, connector):
        """Test that fetching without context manager raises an error."""
        with pytest.raises(RuntimeError, match="not initialized"):
            async for _ in connector.fetch_all_resources():
                pass
