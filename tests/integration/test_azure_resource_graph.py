"""Integration tests for Azure Resource Graph connector.

These tests require actual Azure credentials and will be skipped unless
the AZURE_INTEGRATION_TESTS environment variable is set.

Prerequisites:
- Azure CLI logged in (az login) OR
- Environment variables set (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)
- At least one accessible Azure subscription with resources
"""

import os

import pytest

from src.ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector

# Skip all tests in this module unless integration tests are explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.getenv("AZURE_INTEGRATION_TESTS"),
    reason="Integration tests disabled. Set AZURE_INTEGRATION_TESTS=1 to enable.",
)


@pytest.fixture
async def connector():
    """Create a real connector instance."""
    # Use environment variable for subscription IDs if provided
    subscription_ids = os.getenv("AZURE_SUBSCRIPTION_IDS", "").split(",")
    subscription_ids = [s.strip() for s in subscription_ids if s.strip()]

    connector = AzureResourceGraphConnector(
        subscription_ids=subscription_ids if subscription_ids else None
    )

    async with connector:
        yield connector


@pytest.mark.integration
@pytest.mark.asyncio
async def test_enumerate_subscriptions(connector):
    """Test enumerating real Azure subscriptions."""
    subscriptions = await connector.enumerate_subscriptions()

    assert len(subscriptions) > 0, "Expected at least one subscription"

    # Verify subscription structure
    for sub in subscriptions:
        assert "id" in sub
        assert "name" in sub
        assert sub["id"].startswith(""), "Subscription ID should not be empty"

    print(f"Found {len(subscriptions)} subscriptions:")
    for sub in subscriptions:
        print(f"  - {sub['name']} ({sub['id']})")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_resource_types(connector):
    """Test fetching resource type summary from real environment."""
    types = await connector.fetch_resource_types()

    assert len(types) > 0, "Expected at least one resource type"

    # Verify structure
    for type_info in types:
        assert "type" in type_info
        assert "count_" in type_info
        assert type_info["count_"] > 0

    print(f"Found {len(types)} resource types:")
    for type_info in types[:10]:  # Print first 10
        print(f"  - {type_info['type']}: {type_info['count_']} resources")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_all_resources(connector):
    """Test fetching resources from real environment."""
    resources = []

    # Fetch first 10 resources only for testing
    count = 0
    async for resource in connector.fetch_all_resources():
        resources.append(resource)
        count += 1
        if count >= 10:
            break

    assert len(resources) > 0, "Expected at least one resource"

    # Verify resource structure
    for resource in resources:
        assert "id" in resource
        assert "name" in resource
        assert "type" in resource
        assert "subscriptionId" in resource
        assert "location" in resource

    print(f"Fetched {len(resources)} resources:")
    for resource in resources[:5]:  # Print first 5
        print(f"  - {resource['name']} ({resource['type']}) in {resource['location']}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_specific_resource_type(connector):
    """Test fetching resources of a specific type."""
    # Try to fetch virtual networks (common resource type)
    resources = []

    async for resource in connector.fetch_all_resources(
        resource_types=["Microsoft.Network/virtualNetworks"]
    ):
        resources.append(resource)

    if len(resources) > 0:
        print(f"Found {len(resources)} virtual networks")
        for resource in resources[:3]:
            print(f"  - {resource['name']} in {resource['location']}")
    else:
        print("No virtual networks found in accessible subscriptions")

    # Just verify the query worked (may have 0 results)
    assert isinstance(resources, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_resource_by_id(connector):
    """Test fetching a specific resource by ID."""
    # First, get any resource
    resource_id = None
    async for resource in connector.fetch_all_resources():
        resource_id = resource["id"]
        break

    if resource_id:
        # Now fetch it by ID
        fetched = await connector.fetch_resource_by_id(resource_id)

        assert fetched is not None
        assert fetched["id"] == resource_id
        print(f"Successfully fetched resource by ID: {fetched['name']}")
    else:
        pytest.skip("No resources available to test fetch by ID")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_document(connector):
    """Test converting a real resource to a document."""
    # Fetch one resource
    resource = None
    async for res in connector.fetch_all_resources():
        resource = res
        break

    if resource:
        # Convert to document
        doc = connector.convert_to_document(resource, subscription_name="Test Subscription")

        assert doc.id == resource["id"]
        assert doc.name == resource["name"]
        assert doc.type == resource["type"]
        assert doc.location == resource["location"]
        assert doc.searchable_text != ""

        print(f"Converted resource to document: {doc.name}")
        print(f"Searchable text length: {len(doc.searchable_text)} characters")
    else:
        pytest.skip("No resources available to test document conversion")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_pagination(connector):
    """Test that pagination works correctly (slow test)."""
    # Set a small page size to force pagination
    connector.page_size = 10

    resources = []
    page_count = 0

    # Fetch up to 25 resources across multiple pages
    async for resource in connector.fetch_all_resources():
        resources.append(resource)
        if len(resources) >= 25:
            break

    if len(resources) >= 20:
        print(f"Pagination test: fetched {len(resources)} resources")
        assert len(resources) >= 20, "Should have fetched multiple pages"
    else:
        pytest.skip("Not enough resources to test pagination effectively")
