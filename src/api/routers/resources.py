"""Resources API router."""

import logging
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_resource_service, get_graph_builder
from src.api.models.resources import (
    AzureResource,
    TerraformLink,
    ResourceDependency,
    ResourceGraphQueryRequest,
    ResourceGraphQueryResponse,
)
from src.api.services.resource_service import ResourceService
from src.indexing.graph_builder import GraphBuilder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


# IMPORTANT: Specific routes must come BEFORE the greedy /{resource_id:path} route
# Otherwise the greedy route will match everything and specific routes will never be reached

@router.post("/resource-graph/query", response_model=ResourceGraphQueryResponse)
async def resource_graph_query(
    request: ResourceGraphQueryRequest,
    resource_service: ResourceService = Depends(get_resource_service),
):
    """
    Execute a raw Azure Resource Graph query using KQL.

    **Example query:**
    ```kql
    Resources
    | where type == 'microsoft.compute/virtualmachines'
    | where location == 'canadaeast'
    | project name, resourceGroup, location, properties.hardwareProfile.vmSize
    | limit 100
    ```

    **Security:**
    - Queries are validated to prevent injection
    - Semi-colons and SQL comments are blocked
    - Results limited to accessible subscriptions

    **Use cases:**
    - Custom resource queries not covered by other endpoints
    - Complex filtering and aggregations
    - Cross-subscription queries
    """
    logger.info(f"Executing Resource Graph query (length={len(request.query)})")

    # Validate query to prevent injection attacks
    if _is_query_unsafe(request.query):
        raise HTTPException(
            status_code=400,
            detail="Query contains potentially unsafe characters. "
            "Avoid using semicolons (;) or SQL-style comments (--)",
        )

    try:
        # Execute the query
        results = await resource_service.execute_resource_graph_query(
            query=request.query,
            subscriptions=request.subscriptions,
        )

        return ResourceGraphQueryResponse(
            results=results,
            total_records=len(results),
        )

    except Exception as e:
        logger.error(f"Resource Graph query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed: {str(e)}",
        )


@router.get("/{resource_id:path}/terraform", response_model=list[TerraformLink])
async def get_terraform_for_resource(
    resource_id: str,
    resource_service: ResourceService = Depends(get_resource_service),
    graph_builder: GraphBuilder = Depends(get_graph_builder),
):
    """
    Find Terraform code that manages this resource.

    Returns all Terraform resources that are linked to this Azure resource,
    including the source code location in git.

    **Use case:**
    - "What Terraform code created this VM?"
    - "Show me the IaC definition for this resource"
    """
    decoded_id = unquote(resource_id)
    logger.info(f"Finding Terraform code for resource: {decoded_id}")

    try:
        # Query graph database for Terraform links (synchronous call)
        terraform_links = graph_builder.find_terraform_for_resource(decoded_id)

        result: list[TerraformLink] = []
        for link in terraform_links:
            # Fetch full Terraform resource details
            tf_resource = await resource_service.get_terraform_resource(link.get("address", ""))
            if tf_resource:
                # Re-create the model to ensure proper serialization
                result.append(
                    TerraformLink(
                        address=tf_resource.address,
                        type=tf_resource.type,
                        file_path=tf_resource.file_path,
                        line_number=tf_resource.line_number,
                        repo_url=tf_resource.repo_url,
                        branch=tf_resource.branch,
                        source_code=tf_resource.source_code,
                    )
                )

        logger.info(f"Found {len(result)} Terraform resources for {decoded_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to fetch Terraform links: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch Terraform links. Please try again later.",
        )


@router.get("/{resource_id:path}/dependencies", response_model=list[ResourceDependency])
async def get_resource_dependencies(
    resource_id: str,
    direction: str = Query(default="both", pattern="^(in|out|both)$"),
    depth: int = Query(default=2, ge=1, le=5),
    graph_builder: GraphBuilder = Depends(get_graph_builder),
):
    """
    Get resources related to this resource through dependencies.

    **Direction:**
    - **in**: Resources that depend on this resource (downstream)
    - **out**: Resources that this resource depends on (upstream)
    - **both**: All related resources (default)

    **Depth:** Graph traversal depth (1-5), default 2

    **Use cases:**
    - "What resources depend on this VNet?"
    - "Show me all dependencies for this VM"
    - "What will be affected if I delete this resource?"
    """
    decoded_id = unquote(resource_id)
    logger.info(f"Finding dependencies for resource: {decoded_id} (direction={direction}, depth={depth})")

    try:
        # Query graph database for dependencies (synchronous call)
        dependencies = graph_builder.find_dependencies(decoded_id, direction, depth)

        result = []
        for dep in dependencies:
            result.append(
                ResourceDependency(
                    id=dep.get("id", ""),
                    name=dep.get("name", ""),
                    type=dep.get("type", ""),
                    relationship=dep.get("relationship", "related"),
                    direction="upstream" if dep.get("direction") == "in" else "downstream",
                )
            )

        logger.info(f"Found {len(result)} dependencies for {decoded_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to fetch dependencies: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch dependencies. Please try again later.",
        )


# Greedy path route - MUST BE LAST to avoid matching specific routes above
@router.get("/{resource_id:path}", response_model=AzureResource)
async def get_resource(
    resource_id: str,
    resource_service: ResourceService = Depends(get_resource_service),
):
    """
    Get full details for an Azure resource.

    The resource_id should be the full Azure Resource ID, URL encoded.

    **Example:**
    ```
    /subscriptions/xxx/resourceGroups/yyy/providers/Microsoft.Compute/virtualMachines/zzz
    ```

    Returns resource details including properties, tags, SKU, and location.
    """
    decoded_id = unquote(resource_id)
    logger.info(f"Fetching resource: {decoded_id}")

    resource = await resource_service.get_resource(decoded_id)

    if not resource:
        raise HTTPException(status_code=404, detail=f"Resource not found: {decoded_id}")

    return resource


def _is_query_unsafe(query: str) -> bool:
    """Check if a query contains potentially unsafe characters.

    Args:
        query: KQL query string

    Returns:
        True if query appears unsafe, False otherwise
    """
    # Block semicolons (command chaining)
    if ";" in query:
        return True

    # Block SQL-style comments
    if "--" in query:
        return True

    # Additional checks could be added here (e.g., EXEC, DROP, etc.)
    # but KQL is generally safer than SQL

    return False
