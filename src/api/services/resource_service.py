"""Resource service for fetching and querying Azure resources."""

import logging
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions as cosmos_exceptions

from src.api.models.resources import AzureResource, TerraformLink
from src.ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector

logger = logging.getLogger(__name__)


class ResourceService:
    """Service for managing Azure resources and Terraform links.

    This service provides access to:
    - Azure resources stored in Cosmos DB
    - Terraform resources from Cosmos DB
    - Direct Resource Graph queries
    """

    def __init__(
        self,
        cosmos_client: CosmosClient,
        database_name: str,
        container_name: str,
        arg_connector: AzureResourceGraphConnector,
    ):
        """Initialize the resource service.

        Args:
            cosmos_client: Cosmos DB client
            database_name: Database name
            container_name: Container name for documents
            arg_connector: Azure Resource Graph connector
        """
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.arg_connector = arg_connector

    async def get_resource(self, resource_id: str) -> AzureResource | None:
        """Get an Azure resource by ID from Cosmos DB.

        Args:
            resource_id: Full Azure resource ID

        Returns:
            AzureResource if found, None otherwise
        """
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            # Query for the resource document
            query = "SELECT * FROM c WHERE c.id = @resource_id AND c.doc_type = 'azure_resource'"
            parameters = [{"name": "@resource_id", "value": resource_id}]

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(item)

            if not items:
                logger.info(f"Resource not found in Cosmos DB: {resource_id}")
                return None

            doc = items[0]

            # Map document to AzureResource model
            return AzureResource(
                id=doc.get("id", ""),
                name=doc.get("name", ""),
                type=doc.get("type", ""),
                resource_group=doc.get("resource_group", ""),
                subscription_id=doc.get("subscription_id", ""),
                subscription_name=doc.get("subscription_name", ""),
                location=doc.get("location", ""),
                tags=doc.get("tags", {}),
                sku=doc.get("sku"),
                kind=doc.get("kind"),
                properties=doc.get("properties", {}),
            )

        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error fetching resource: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching resource: {e}", exc_info=True)
            return None

    async def get_terraform_resource(self, address: str) -> TerraformLink | None:
        """Get a Terraform resource by address from Cosmos DB.

        Args:
            address: Terraform resource address (e.g., "azurerm_virtual_machine.example")

        Returns:
            TerraformLink if found, None otherwise
        """
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            # Query for the Terraform resource document
            query = "SELECT * FROM c WHERE c.address = @address AND c.doc_type = 'terraform_resource'"
            parameters = [{"name": "@address", "value": address}]

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(item)

            if not items:
                logger.info(f"Terraform resource not found: {address}")
                return None

            doc = items[0]

            # Map document to TerraformLink model
            return TerraformLink(
                address=doc.get("address", ""),
                type=doc.get("type", ""),
                file_path=doc.get("file_path", ""),
                line_number=doc.get("line_number", 0),
                repo_url=doc.get("repo_url", ""),
                branch=doc.get("branch", "main"),
                source_code=doc.get("source_code", ""),
            )

        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error fetching Terraform resource: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Terraform resource: {e}", exc_info=True)
            return None

    async def execute_resource_graph_query(
        self,
        query: str,
        subscriptions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a raw Azure Resource Graph query.

        Args:
            query: KQL query string
            subscriptions: Optional list of subscription IDs to query

        Returns:
            List of query results

        Raises:
            Exception: If query execution fails
        """
        try:
            logger.info(f"Executing Resource Graph query (subscriptions={subscriptions})")

            results = []
            async for result in self.arg_connector.query_resources(
                query=query,
                subscriptions=subscriptions,
            ):
                results.append(result)

            logger.info(f"Resource Graph query returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Resource Graph query failed: {e}", exc_info=True)
            raise
