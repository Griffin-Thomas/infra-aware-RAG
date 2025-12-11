"""Resource service for fetching and querying Azure resources."""

import logging
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions as cosmos_exceptions

from src.api.models.resources import AzureResource, TerraformLink, ResourceDependency
from src.ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector
from src.indexing.graph_builder import GraphBuilder

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
        graph_builder: GraphBuilder | None = None,
    ):
        """Initialize the resource service.

        Args:
            cosmos_client: Cosmos DB client
            database_name: Database name
            container_name: Container name for documents
            arg_connector: Azure Resource Graph connector
            graph_builder: Graph builder for dependency queries
        """
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.arg_connector = arg_connector
        self.graph_builder = graph_builder

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

            # The connector requires async with initialization
            if subscriptions:
                self.arg_connector.subscription_ids = subscriptions

            results = []
            async with self.arg_connector:
                async for result in self.arg_connector.fetch_all_resources(query=query):
                    results.append(result)

            logger.info(f"Resource Graph query returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Resource Graph query failed: {e}", exc_info=True)
            raise

    async def get_terraform_for_resource(
        self,
        resource_id: str,
    ) -> list[TerraformLink]:
        """Get Terraform resources that manage a given Azure resource.

        Args:
            resource_id: Full Azure resource ID

        Returns:
            List of TerraformLink objects
        """
        try:
            # Use graph builder if available
            if self.graph_builder:
                tf_resources = self.graph_builder.find_terraform_for_resource(resource_id)
                return [
                    TerraformLink(
                        address=tf.get("address", ""),
                        type=tf.get("type", ""),
                        file_path=tf.get("file_path", ""),
                        line_number=tf.get("line_number", 0),
                        repo_url=tf.get("repo_url", ""),
                        branch=tf.get("branch", "main"),
                        source_code=tf.get("source_code", ""),
                    )
                    for tf in tf_resources
                ]

            # Fall back to Cosmos DB query
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            query = """
                SELECT * FROM c
                WHERE c.doc_type = 'terraform_resource'
                AND c.azure_resource_id = @resource_id
            """
            parameters = [{"name": "@resource_id", "value": resource_id}]

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(
                    TerraformLink(
                        address=item.get("address", ""),
                        type=item.get("type", ""),
                        file_path=item.get("file_path", ""),
                        line_number=item.get("line_number", 0),
                        repo_url=item.get("repo_url", ""),
                        branch=item.get("branch", "main"),
                        source_code=item.get("source_code", ""),
                    )
                )

            return items

        except Exception as e:
            logger.error(f"Error fetching Terraform for resource: {e}", exc_info=True)
            return []

    async def get_dependencies(
        self,
        resource_id: str,
        direction: str = "both",
        depth: int = 2,
    ) -> list[ResourceDependency]:
        """Get dependencies for an Azure resource.

        Args:
            resource_id: Full Azure resource ID
            direction: Traversal direction - "in", "out", or "both"
            depth: Maximum traversal depth

        Returns:
            List of ResourceDependency objects
        """
        try:
            if not self.graph_builder:
                logger.warning("Graph builder not configured, returning empty dependencies")
                return []

            paths = self.graph_builder.find_dependencies(
                resource_id=resource_id,
                direction=direction,
                depth=depth,
            )

            dependencies = []
            seen_ids = set()

            for path in paths:
                # Path can be a list of vertices/edges
                if isinstance(path, (list, tuple)):
                    for vertex in path:
                        if isinstance(vertex, dict) and "id" in vertex:
                            vid = vertex["id"]
                            if vid not in seen_ids and vid != resource_id:
                                seen_ids.add(vid)
                                dependencies.append(
                                    ResourceDependency(
                                        id=vid,
                                        name=vertex.get("name", ""),
                                        type=vertex.get("type", ""),
                                        relationship="depends_on",
                                        direction="upstream" if direction == "out" else "downstream",
                                    )
                                )
                elif isinstance(path, dict) and "id" in path:
                    vid = path["id"]
                    if vid not in seen_ids and vid != resource_id:
                        seen_ids.add(vid)
                        dependencies.append(
                            ResourceDependency(
                                id=vid,
                                name=path.get("name", ""),
                                type=path.get("type", ""),
                                relationship="depends_on",
                                direction="both",
                            )
                        )

            return dependencies

        except Exception as e:
            logger.error(f"Error fetching dependencies: {e}", exc_info=True)
            return []

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """List all accessible Azure subscriptions.

        Returns:
            List of subscription dictionaries with id, name, and state
        """
        try:
            async with self.arg_connector:
                return await self.arg_connector.enumerate_subscriptions()
        except Exception as e:
            logger.error(f"Error listing subscriptions: {e}", exc_info=True)
            return []

    async def get_resource_types_summary(
        self,
        subscription_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get summary of resource types with counts.

        Args:
            subscription_id: Optional subscription ID to filter

        Returns:
            List of dictionaries with 'type' and 'count' keys
        """
        try:
            if subscription_id:
                self.arg_connector.subscription_ids = [subscription_id]
            else:
                self.arg_connector.subscription_ids = []

            async with self.arg_connector:
                return await self.arg_connector.fetch_resource_types()
        except Exception as e:
            logger.error(f"Error getting resource types summary: {e}", exc_info=True)
            return []
