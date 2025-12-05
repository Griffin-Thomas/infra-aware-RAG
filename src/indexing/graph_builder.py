"""Graph database builder for infrastructure relationships using Cosmos DB Gremlin API."""

import logging
from typing import Any

from gremlin_python.driver import client, serializer

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds and populates the infrastructure graph in Cosmos DB Gremlin API.

    The graph models relationships between:
    - Subscriptions → Resource Groups → Azure Resources
    - Terraform Resources → Azure Resources
    - Git Commits → Terraform Files
    - Resource Dependencies
    """

    def __init__(
        self,
        endpoint: str,
        database: str,
        graph: str,
        key: str,
    ):
        """Initialize graph builder.

        Args:
            endpoint: Cosmos DB endpoint (e.g., https://myaccount.documents.azure.com:443/)
            database: Database name
            graph: Graph/collection name
            key: Account key for authentication
        """
        self.endpoint = endpoint
        self.database = database
        self.graph = graph

        # Build Gremlin endpoint from Cosmos DB endpoint
        # Convert https://account.documents.azure.com:443/ to wss://account.gremlin.cosmos.azure.com:443/
        gremlin_endpoint = endpoint.replace("https://", "wss://").replace(
            ".documents.azure.com:443/", ".gremlin.cosmos.azure.com:443/"
        )

        logger.info(f"Connecting to Gremlin endpoint: {gremlin_endpoint}")

        # Initialize Gremlin client
        self.client = client.Client(
            gremlin_endpoint,
            "g",
            username=f"/dbs/{database}/colls/{graph}",
            password=key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )

    def add_subscription(self, sub_id: str, name: str, tenant_id: str):
        """Add or update a subscription vertex.

        Args:
            sub_id: Subscription ID
            name: Subscription name
            tenant_id: Azure tenant ID
        """
        query = """
        g.V().has('subscription', 'id', sub_id).fold()
        .coalesce(
            unfold(),
            addV('subscription').property('id', sub_id)
        )
        .property('name', name)
        .property('tenant_id', tenant_id)
        """

        try:
            self.client.submit(query, {"sub_id": sub_id, "name": name, "tenant_id": tenant_id})
            logger.debug(f"Added/updated subscription: {sub_id}")
        except Exception as e:
            logger.error(f"Failed to add subscription {sub_id}: {e}")
            raise

    def add_resource_group(self, rg_id: str, name: str, sub_id: str, location: str):
        """Add or update a resource group vertex with edge to subscription.

        Args:
            rg_id: Resource group ID (full Azure resource ID)
            name: Resource group name
            sub_id: Parent subscription ID
            location: Azure region
        """
        # Add or update resource group vertex
        vertex_query = """
        g.V().has('resource_group', 'id', rg_id).fold()
        .coalesce(
            unfold(),
            addV('resource_group').property('id', rg_id)
        )
        .property('name', name)
        .property('location', location)
        """

        try:
            self.client.submit(
                vertex_query,
                {"rg_id": rg_id, "name": name, "location": location},
            )
            logger.debug(f"Added/updated resource group: {rg_id}")
        except Exception as e:
            logger.error(f"Failed to add resource group {rg_id}: {e}")
            raise

        # Add edge from subscription to resource group
        edge_query = """
        g.V().has('subscription', 'id', sub_id)
        .coalesce(
            outE('contains').where(inV().has('resource_group', 'id', rg_id)),
            addE('contains').to(g.V().has('resource_group', 'id', rg_id))
        )
        """

        try:
            self.client.submit(edge_query, {"sub_id": sub_id, "rg_id": rg_id})
            logger.debug(f"Added contains edge: {sub_id} -> {rg_id}")
        except Exception as e:
            logger.error(f"Failed to add subscription->resource group edge: {e}")
            raise

    def add_azure_resource(self, resource: dict[str, Any]):
        """Add or update an Azure resource vertex with edge to resource group.

        Args:
            resource: Dictionary with resource properties:
                - id: Azure resource ID
                - type: Resource type (e.g., Microsoft.Compute/virtualMachines)
                - name: Resource name
                - location: Azure region
                - subscription_id: Subscription ID
                - resource_group: Resource group name
        """
        # Add or update resource vertex
        vertex_query = """
        g.V().has('azure_resource', 'id', res_id).fold()
        .coalesce(
            unfold(),
            addV('azure_resource').property('id', res_id)
        )
        .property('type', res_type)
        .property('name', name)
        .property('location', location)
        """

        try:
            self.client.submit(
                vertex_query,
                {
                    "res_id": resource["id"],
                    "res_type": resource["type"],
                    "name": resource["name"],
                    "location": resource.get("location", ""),
                },
            )
            logger.debug(f"Added/updated Azure resource: {resource['id']}")
        except Exception as e:
            logger.error(f"Failed to add Azure resource {resource['id']}: {e}")
            raise

        # Add edge from resource group to resource
        rg_id = f"/subscriptions/{resource['subscription_id']}/resourceGroups/{resource['resource_group']}"
        edge_query = """
        g.V().has('resource_group', 'id', rg_id)
        .coalesce(
            outE('contains').where(inV().has('azure_resource', 'id', res_id)),
            addE('contains').to(g.V().has('azure_resource', 'id', res_id))
        )
        """

        try:
            self.client.submit(edge_query, {"rg_id": rg_id, "res_id": resource["id"]})
            logger.debug(f"Added contains edge: {rg_id} -> {resource['id']}")
        except Exception as e:
            logger.error(f"Failed to add resource group->resource edge: {e}")
            raise

    def add_resource_dependency(
        self, from_id: str, to_id: str, dep_type: str = "depends_on"
    ):
        """Add a dependency edge between Azure resources.

        Args:
            from_id: Source resource ID
            to_id: Target resource ID
            dep_type: Edge label (default: "depends_on")
        """
        query = """
        g.V().has('azure_resource', 'id', from_id)
        .coalesce(
            outE(dep_type).where(inV().has('azure_resource', 'id', to_id)),
            addE(dep_type).to(g.V().has('azure_resource', 'id', to_id))
        )
        """

        try:
            self.client.submit(
                query, {"from_id": from_id, "to_id": to_id, "dep_type": dep_type}
            )
            logger.debug(f"Added dependency edge: {from_id} -{dep_type}-> {to_id}")
        except Exception as e:
            logger.error(f"Failed to add dependency {from_id} -> {to_id}: {e}")
            raise

    def add_terraform_resource(self, tf_resource: dict[str, Any]):
        """Add or update a Terraform resource vertex.

        Args:
            tf_resource: Dictionary with Terraform resource properties:
                - address: Terraform resource address (e.g., azurerm_resource_group.main)
                - type: Terraform resource type
                - file_path: Path to .tf file
                - repo_url: Git repository URL
                - branch: Git branch
        """
        query = """
        g.V().has('terraform_resource', 'address', tf_addr).fold()
        .coalesce(
            unfold(),
            addV('terraform_resource').property('address', tf_addr)
        )
        .property('type', tf_type)
        .property('file_path', file_path)
        .property('repo_url', repo_url)
        .property('branch', branch)
        """

        try:
            self.client.submit(
                query,
                {
                    "tf_addr": tf_resource["address"],
                    "tf_type": tf_resource["type"],
                    "file_path": tf_resource["file_path"],
                    "repo_url": tf_resource.get("repo_url", ""),
                    "branch": tf_resource.get("branch", ""),
                },
            )
            logger.debug(f"Added/updated Terraform resource: {tf_resource['address']}")
        except Exception as e:
            logger.error(f"Failed to add Terraform resource {tf_resource['address']}: {e}")
            raise

    def link_terraform_to_azure(self, tf_address: str, azure_id: str):
        """Link a Terraform resource to the Azure resource it manages.

        Args:
            tf_address: Terraform resource address
            azure_id: Azure resource ID
        """
        query = """
        g.V().has('terraform_resource', 'address', tf_addr)
        .coalesce(
            outE('manages').where(inV().has('azure_resource', 'id', azure_id)),
            addE('manages').to(g.V().has('azure_resource', 'id', azure_id))
        )
        """

        try:
            self.client.submit(query, {"tf_addr": tf_address, "azure_id": azure_id})
            logger.debug(f"Linked Terraform resource {tf_address} to Azure resource {azure_id}")
        except Exception as e:
            logger.error(f"Failed to link {tf_address} -> {azure_id}: {e}")
            raise

    def find_dependencies(
        self, resource_id: str, direction: str = "both", depth: int = 2
    ) -> list[dict[str, Any]]:
        """Find resources connected to a given resource by traversing the graph.

        Args:
            resource_id: Azure resource ID to start from
            direction: Traversal direction - "in" (dependents), "out" (dependencies), or "both"
            depth: Maximum traversal depth

        Returns:
            List of paths from the resource to connected resources
        """
        if direction == "in":
            # Find resources that depend on this resource
            query = f"g.V().has('azure_resource', 'id', res_id).repeat(inE().outV()).times({depth}).path()"
        elif direction == "out":
            # Find resources this resource depends on
            query = f"g.V().has('azure_resource', 'id', res_id).repeat(outE().inV()).times({depth}).path()"
        else:
            # Find all connected resources
            query = f"g.V().has('azure_resource', 'id', res_id).repeat(bothE().otherV()).times({depth}).dedup().path()"

        try:
            results = self.client.submit(query, {"res_id": resource_id})
            paths = list(results)
            logger.debug(f"Found {len(paths)} paths from resource {resource_id}")
            return paths
        except Exception as e:
            logger.error(f"Failed to find dependencies for {resource_id}: {e}")
            raise

    def find_terraform_for_resource(self, azure_id: str) -> list[dict[str, Any]]:
        """Find Terraform resources that manage a given Azure resource.

        Args:
            azure_id: Azure resource ID

        Returns:
            List of Terraform resource info (address, file_path, repo_url)
        """
        query = """
        g.V().has('azure_resource', 'id', azure_id)
        .inE('manages').outV()
        .project('address', 'file_path', 'repo_url', 'branch')
        .by('address').by('file_path').by('repo_url').by('branch')
        """

        try:
            results = self.client.submit(query, {"azure_id": azure_id})
            tf_resources = list(results)
            logger.debug(f"Found {len(tf_resources)} Terraform resources managing {azure_id}")
            return tf_resources
        except Exception as e:
            logger.error(f"Failed to find Terraform for resource {azure_id}: {e}")
            raise

    def find_resource_group_resources(self, rg_id: str) -> list[dict[str, Any]]:
        """Find all Azure resources in a resource group.

        Args:
            rg_id: Resource group ID

        Returns:
            List of resource info (id, type, name, location)
        """
        query = """
        g.V().has('resource_group', 'id', rg_id)
        .outE('contains').inV().hasLabel('azure_resource')
        .project('id', 'type', 'name', 'location')
        .by('id').by('type').by('name').by('location')
        """

        try:
            results = self.client.submit(query, {"rg_id": rg_id})
            resources = list(results)
            logger.debug(f"Found {len(resources)} resources in resource group {rg_id}")
            return resources
        except Exception as e:
            logger.error(f"Failed to find resources in resource group {rg_id}: {e}")
            raise

    def clear_graph(self):
        """Clear all vertices and edges from the graph.

        WARNING: This deletes all data in the graph!
        """
        query = "g.V().drop()"

        try:
            self.client.submit(query, {})
            logger.warning("Cleared all vertices and edges from graph")
        except Exception as e:
            logger.error(f"Failed to clear graph: {e}")
            raise

    def close(self):
        """Close the Gremlin client and cleanup resources."""
        if self.client:
            self.client.close()
            logger.info("Closed Gremlin client")
