"""Terraform service for fetching and analyzing Terraform resources and plans."""

import logging
from datetime import datetime
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions as cosmos_exceptions

from src.api.models.terraform import (
    TerraformResource,
    TerraformPlan,
    PlannedChange,
    PlanAnalysis,
    ParsedPlan,
)

logger = logging.getLogger(__name__)


class TerraformService:
    """Service for managing Terraform resources and plans.

    This service provides access to:
    - Terraform resources from Cosmos DB
    - Terraform plans from Cosmos DB
    - Plan analysis functionality
    """

    def __init__(
        self,
        cosmos_client: CosmosClient,
        database_name: str,
        container_name: str,
    ):
        """Initialize the Terraform service.

        Args:
            cosmos_client: Cosmos DB client
            database_name: Database name
            container_name: Container name for documents
        """
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name

    async def list_resources(
        self,
        repo_url: str | None = None,
        resource_type: str | None = None,
        file_path: str | None = None,
        limit: int = 50,
    ) -> list[TerraformResource]:
        """List Terraform resources with optional filters.

        Args:
            repo_url: Filter by repository URL
            resource_type: Filter by resource type
            file_path: Filter by file path
            limit: Maximum number of results

        Returns:
            List of Terraform resources
        """
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            # Build query with filters
            query = "SELECT * FROM c WHERE c.doc_type = 'terraform_resource'"
            parameters = []

            if repo_url:
                query += " AND c.repo_url = @repo_url"
                parameters.append({"name": "@repo_url", "value": repo_url})

            if resource_type:
                query += " AND c.type = @resource_type"
                parameters.append({"name": "@resource_type", "value": resource_type})

            if file_path:
                query += " AND c.file_path = @file_path"
                parameters.append({"name": "@file_path", "value": file_path})

            query += f" ORDER BY c.file_path OFFSET 0 LIMIT {limit}"

            logger.info(f"Querying Terraform resources with filters: repo_url={repo_url}, type={resource_type}, file_path={file_path}")

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(self._map_to_terraform_resource(item))

            logger.info(f"Found {len(items)} Terraform resources")
            return items

        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error listing Terraform resources: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing Terraform resources: {e}", exc_info=True)
            return []

    async def get_resource(self, address: str, repo_url: str) -> TerraformResource | None:
        """Get a specific Terraform resource by address and repository.

        Args:
            address: Terraform resource address
            repo_url: Repository URL

        Returns:
            TerraformResource if found, None otherwise
        """
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            query = """
                SELECT * FROM c
                WHERE c.doc_type = 'terraform_resource'
                AND c.address = @address
                AND c.repo_url = @repo_url
            """
            parameters = [
                {"name": "@address", "value": address},
                {"name": "@repo_url", "value": repo_url},
            ]

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(item)

            if not items:
                logger.info(f"Terraform resource not found: {address} in {repo_url}")
                return None

            return self._map_to_terraform_resource(items[0])

        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error fetching Terraform resource: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Terraform resource: {e}", exc_info=True)
            return None

    async def list_plans(
        self,
        repo_url: str | None = None,
        since: datetime | None = None,
        limit: int = 10,
    ) -> list[TerraformPlan]:
        """List Terraform plans with optional filters.

        Args:
            repo_url: Filter by repository URL
            since: Filter plans after this timestamp
            limit: Maximum number of results

        Returns:
            List of Terraform plans
        """
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            query = "SELECT * FROM c WHERE c.doc_type = 'terraform_plan'"
            parameters = []

            if repo_url:
                query += " AND c.repo_url = @repo_url"
                parameters.append({"name": "@repo_url", "value": repo_url})

            if since:
                query += " AND c.timestamp >= @since"
                parameters.append({"name": "@since", "value": since.isoformat()})

            query += f" ORDER BY c.timestamp DESC OFFSET 0 LIMIT {limit}"

            logger.info(f"Querying Terraform plans with filters: repo_url={repo_url}, since={since}")

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(self._map_to_terraform_plan(item))

            logger.info(f"Found {len(items)} Terraform plans")
            return items

        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error listing Terraform plans: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing Terraform plans: {e}", exc_info=True)
            return []

    async def get_plan(self, plan_id: str) -> TerraformPlan | None:
        """Get a specific Terraform plan by ID.

        Args:
            plan_id: Plan ID

        Returns:
            TerraformPlan if found, None otherwise
        """
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(self.container_name)

            query = "SELECT * FROM c WHERE c.id = @plan_id AND c.doc_type = 'terraform_plan'"
            parameters = [{"name": "@plan_id", "value": plan_id}]

            items = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            ):
                items.append(item)

            if not items:
                logger.info(f"Terraform plan not found: {plan_id}")
                return None

            return self._map_to_terraform_plan(items[0])

        except cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB error fetching Terraform plan: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Terraform plan: {e}", exc_info=True)
            return None

    async def analyze_plan(self, plan: TerraformPlan) -> PlanAnalysis:
        """Generate AI analysis of a Terraform plan.

        Args:
            plan: Terraform plan to analyze

        Returns:
            PlanAnalysis with summary, risk level, and recommendations
        """
        # Note: AI-based analysis will be implemented in Phase 4 (LLM Orchestration).
        # For now, return a basic analysis based on plan statistics.

        total_changes = plan.add + plan.change + plan.destroy

        # Determine risk level based on changes
        if plan.destroy > 0 or total_changes > 20:
            risk_level = "high"
        elif total_changes > 5:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Generate summary
        summary = f"Plan will add {plan.add}, change {plan.change}, and destroy {plan.destroy} resources."

        # Extract key changes
        key_changes = []
        for change in plan.changes[:5]:  # Top 5 changes
            key_changes.append(f"{change.action.upper()}: {change.address}")

        # Generate recommendations
        recommendations = []
        if plan.destroy > 0:
            recommendations.append("Review all resources marked for destruction carefully")
        if total_changes > 10:
            recommendations.append("Consider breaking this plan into smaller, incremental changes")
        if plan.add > 0:
            recommendations.append("Verify that new resources have appropriate tags and naming conventions")

        return PlanAnalysis(
            summary=summary,
            risk_level=risk_level,
            key_changes=key_changes,
            recommendations=recommendations,
        )

    def parse_plan(self, plan_json: dict[str, Any]) -> ParsedPlan:
        """Parse a Terraform plan JSON.

        Args:
            plan_json: Terraform plan JSON (output of `terraform show -json plan.tfplan`)

        Returns:
            ParsedPlan with structured changes

        Raises:
            ValueError: If plan JSON is invalid
        """
        try:
            # Extract resource changes from plan JSON
            resource_changes = plan_json.get("resource_changes", [])

            add_count = 0
            change_count = 0
            destroy_count = 0
            changes = []

            for rc in resource_changes:
                change = rc.get("change", {})
                actions = change.get("actions", [])

                # Determine action type
                # Check for replace first - Terraform represents this as ["delete", "create"]
                if "delete" in actions and "create" in actions:
                    # Replacements count as both a destroy and a create
                    destroy_count += 1
                    add_count += 1
                    action = "replace"
                elif "create" in actions:
                    add_count += 1
                    action = "create"
                elif "delete" in actions:
                    destroy_count += 1
                    action = "delete"
                elif "update" in actions:
                    change_count += 1
                    action = "update"
                else:
                    continue

                # Extract changed attributes
                changed_attrs = []
                before = change.get("before", {})
                after = change.get("after", {})

                if before and after:
                    # Find attributes that changed
                    all_keys = set(before.keys()) | set(after.keys())
                    for key in all_keys:
                        if before.get(key) != after.get(key):
                            changed_attrs.append(key)

                # Create PlannedChange
                address = rc.get("address", "")
                resource_type = rc.get("type", "")

                summary = f"{action.capitalize()} {resource_type} resource"
                if changed_attrs:
                    summary += f" (changing: {', '.join(changed_attrs[:3])})"

                changes.append(
                    PlannedChange(
                        address=address,
                        action=action,
                        resource_type=resource_type,
                        changed_attributes=changed_attrs,
                        summary=summary,
                    )
                )

            return ParsedPlan(
                add=add_count,
                change=change_count,
                destroy=destroy_count,
                changes=changes,
            )

        except Exception as e:
            logger.error(f"Failed to parse Terraform plan: {e}", exc_info=True)
            raise ValueError(f"Invalid Terraform plan JSON: {e}")

    def _map_to_terraform_resource(self, doc: dict[str, Any]) -> TerraformResource:
        """Map Cosmos DB document to TerraformResource model."""
        return TerraformResource(
            address=doc.get("address", ""),
            type=doc.get("type", ""),
            name=doc.get("name", ""),
            module_path=doc.get("module_path"),
            file_path=doc.get("file_path", ""),
            line_number=doc.get("line_number", 0),
            repo_url=doc.get("repo_url", ""),
            branch=doc.get("branch", "main"),
            provider=doc.get("provider", ""),
            source_code=doc.get("source_code", ""),
            dependencies=doc.get("dependencies", []),
            azure_resource_id=doc.get("azure_resource_id"),
        )

    def _map_to_terraform_plan(self, doc: dict[str, Any]) -> TerraformPlan:
        """Map Cosmos DB document to TerraformPlan model."""
        # Parse timestamp
        timestamp_str = doc.get("timestamp", "")
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now()

        # Parse changes
        changes = []
        for change_data in doc.get("changes", []):
            changes.append(
                PlannedChange(
                    address=change_data.get("address", ""),
                    action=change_data.get("action", ""),
                    resource_type=change_data.get("resource_type", ""),
                    changed_attributes=change_data.get("changed_attributes", []),
                    summary=change_data.get("summary", ""),
                )
            )

        return TerraformPlan(
            id=doc.get("id", ""),
            repo_url=doc.get("repo_url", ""),
            branch=doc.get("branch", "main"),
            commit_sha=doc.get("commit_sha", ""),
            timestamp=timestamp,
            add=doc.get("add", 0),
            change=doc.get("change", 0),
            destroy=doc.get("destroy", 0),
            changes=changes,
        )
