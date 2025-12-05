"""Azure Resource Graph connector for querying Azure resources."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.resourcegraph.aio import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.models.documents import AzureResourceDocument

logger = logging.getLogger(__name__)


class AzureResourceGraphConnector:
    """Connector for Azure Resource Graph queries.

    This connector provides async methods to query Azure resources across
    subscriptions using the Azure Resource Graph API. It handles pagination,
    retries, and converts raw resource data into AzureResourceDocument objects.
    """

    # Default query to fetch all resources
    DEFAULT_QUERY = """
    Resources
    | project id, name, type, resourceGroup, subscriptionId, location,
              tags, sku, kind, managedBy, properties,
              createdTime, changedTime
    | order by id asc
    """

    def __init__(
        self,
        subscription_ids: list[str] | None = None,
        credential: DefaultAzureCredential | None = None,
        page_size: int = 1000,
        max_retries: int = 3,
    ):
        """Initialize the connector.

        Args:
            subscription_ids: List of subscription IDs to query. If None or empty,
                queries all accessible subscriptions.
            credential: Azure credential for authentication. Uses DefaultAzureCredential
                if not provided.
            page_size: Number of resources to fetch per page (max 1000)
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.subscription_ids = subscription_ids or []
        self.credential = credential or DefaultAzureCredential()
        self.page_size = min(page_size, 1000)  # Azure max is 1000
        self.max_retries = max_retries
        self._client: ResourceGraphClient | None = None

    async def __aenter__(self) -> "AzureResourceGraphConnector":
        """Async context manager entry."""
        self._client = ResourceGraphClient(self.credential)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.close()
        await self.credential.close()

    async def fetch_all_resources(
        self,
        query: str | None = None,
        resource_types: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Fetch all resources matching the query.

        Args:
            query: Custom KQL query (uses DEFAULT_QUERY if not provided)
            resource_types: Optional filter for specific resource types

        Yields:
            Resource dictionaries from Azure Resource Graph

        Raises:
            AzureError: If the query fails after all retries
        """
        if not self._client:
            raise RuntimeError("Connector not initialized. Use 'async with' context manager.")

        if query is None:
            query = self.DEFAULT_QUERY

        # Add resource type filter if provided
        if resource_types:
            type_filter = " or ".join(f"type == '{t}'" for t in resource_types)
            query = query.replace("| order by id asc", f"| where {type_filter}\n| order by id asc")

        skip_token = None
        page_count = 0

        while True:
            options = QueryRequestOptions(
                top=self.page_size,
                skip_token=skip_token,
            )

            request = QueryRequest(
                subscriptions=self.subscription_ids if self.subscription_ids else None,
                query=query,
                options=options,
            )

            # Execute query with retry logic
            response = await self._execute_query_with_retry(request)

            # Yield resources from this page
            for row in response.data:
                yield row

            page_count += 1
            logger.debug(f"Fetched page {page_count} with {len(response.data)} resources")

            # Check for more pages
            skip_token = response.skip_token
            if not skip_token:
                logger.info(f"Completed fetching {page_count} pages of resources")
                break

    async def _execute_query_with_retry(self, request: QueryRequest) -> Any:
        """Execute a Resource Graph query with exponential backoff retry.

        Args:
            request: The query request to execute

        Returns:
            Query response from Azure Resource Graph

        Raises:
            AzureError: If all retry attempts fail
        """
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(AzureError),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        ):
            with attempt:
                logger.debug(
                    f"Executing Resource Graph query (attempt {attempt.retry_state.attempt_number})"
                )
                return await self._client.resources(request)

    async def fetch_resource_by_id(self, resource_id: str) -> dict[str, Any] | None:
        """Fetch a single resource by its ID.

        Args:
            resource_id: The full Azure resource ID

        Returns:
            Resource dictionary or None if not found
        """
        # Escape single quotes in resource ID
        escaped_id = resource_id.replace("'", "''")

        query = f"""
        Resources
        | where id == '{escaped_id}'
        | project id, name, type, resourceGroup, subscriptionId, location,
                  tags, sku, kind, managedBy, properties,
                  createdTime, changedTime
        """

        async for resource in self.fetch_all_resources(query=query):
            return resource
        return None

    async def fetch_resource_types(self) -> list[dict[str, Any]]:
        """Fetch summary of all resource types and counts.

        Returns:
            List of dictionaries with 'type' and 'count_' keys
        """
        query = """
        Resources
        | summarize count() by type
        | order by count_ desc
        """

        types = []
        async for row in self.fetch_all_resources(query=query):
            types.append(row)
        return types

    async def enumerate_subscriptions(self) -> list[dict[str, Any]]:
        """Enumerate all accessible subscriptions.

        Returns:
            List of subscription dictionaries with id, name, and state
        """
        query = """
        ResourceContainers
        | where type == 'microsoft.resources/subscriptions'
        | project subscriptionId, name, properties
        """

        subscriptions = []
        async for row in self.fetch_all_resources(query=query):
            subscriptions.append(
                {
                    "id": row.get("subscriptionId"),
                    "name": row.get("name"),
                    "state": row.get("properties", {}).get("state"),
                }
            )
        return subscriptions

    def convert_to_document(
        self, resource: dict[str, Any], subscription_name: str | None = None
    ) -> AzureResourceDocument:
        """Convert a raw resource dictionary to an AzureResourceDocument.

        Args:
            resource: Raw resource data from Resource Graph
            subscription_name: Optional subscription name (fetched separately)

        Returns:
            AzureResourceDocument instance
        """
        doc = AzureResourceDocument(
            id=resource["id"],
            name=resource["name"],
            type=resource["type"],
            resource_group=resource.get("resourceGroup", ""),
            subscription_id=resource["subscriptionId"],
            subscription_name=subscription_name or resource["subscriptionId"],
            location=resource["location"],
            tags=resource.get("tags", {}),
            sku=resource.get("sku"),
            kind=resource.get("kind"),
            managed_by=resource.get("managedBy"),
            properties=resource.get("properties", {}),
            created_time=resource.get("createdTime"),
            changed_time=resource.get("changedTime"),
        )

        # Generate searchable text
        doc.searchable_text = doc.generate_searchable_text()

        return doc
