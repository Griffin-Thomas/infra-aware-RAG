"""Tools API router for LLM function calling.

This router provides endpoints for:
1. Listing available tools
2. Executing tool calls from the LLM

Tools are executed by the LLM orchestration layer to interact with
Azure infrastructure, Terraform IaC, and Git history.
"""

import logging
from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import (
    get_search_engine,
    get_resource_service,
    get_terraform_service,
    get_git_service,
)
from src.api.tools.definitions import TOOL_DEFINITIONS, validate_tool_call
from src.search.hybrid_search import HybridSearchEngine
from src.api.services.resource_service import ResourceService
from src.api.services.terraform_service import TerraformService
from src.api.services.git_service import GitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolCallRequest(BaseModel):
    """Request to execute a tool."""

    name: str = Field(..., description="Tool name to execute")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )


class ToolCallResponse(BaseModel):
    """Response from tool execution."""

    name: str = Field(..., description="Tool name that was executed")
    result: Any = Field(default=None, description="Tool execution result")
    error: str | None = Field(default=None, description="Error message if execution failed")


@router.get("")
async def list_tools():
    """
    List all available tools with their definitions.

    Returns tool definitions in OpenAI/Anthropic function calling schema format.
    This endpoint is used by the LLM to discover available tools.

    **Returns:**
    - `tools`: List of tool definitions with name, description, and parameters

    **Use cases:**
    - "What tools are available?"
    - "Show me all available functions"
    """
    logger.info("Listing available tools")
    return {"tools": TOOL_DEFINITIONS}


@router.post("/execute", response_model=ToolCallResponse)
async def execute_tool(
    request: ToolCallRequest,
    search_engine: HybridSearchEngine = Depends(get_search_engine),
    resource_service: ResourceService = Depends(get_resource_service),
    terraform_service: TerraformService = Depends(get_terraform_service),
    git_service: GitService = Depends(get_git_service),
):
    """
    Execute a tool by name with given arguments.

    This endpoint is used by the LLM orchestration layer to execute
    function calls. It validates the tool call and dispatches to the
    appropriate service.

    **Request:**
    - `name`: Tool name (must match a defined tool)
    - `arguments`: Tool arguments as a JSON object

    **Response:**
    - `name`: Tool name that was executed
    - `result`: Tool execution result (structure depends on tool)
    - `error`: Error message if execution failed

    **Error Handling:**
    - Returns error in response rather than HTTP error
    - Allows LLM to handle errors gracefully
    """
    logger.info(f"Executing tool: {request.name} with arguments: {request.arguments}")

    # Validate tool call
    is_valid, error_msg = validate_tool_call(request.name, request.arguments)
    if not is_valid:
        logger.warning(f"Invalid tool call: {error_msg}")
        return ToolCallResponse(name=request.name, result=None, error=error_msg)

    try:
        result = await _execute_tool(
            name=request.name,
            arguments=request.arguments,
            search_engine=search_engine,
            resource_service=resource_service,
            terraform_service=terraform_service,
            git_service=git_service,
        )

        logger.info(f"Tool execution successful: {request.name}")
        return ToolCallResponse(name=request.name, result=result)

    except ValueError as e:
        # Expected errors (e.g., resource not found)
        logger.warning(f"Tool execution failed with ValueError: {e}")
        return ToolCallResponse(name=request.name, result=None, error=str(e))

    except Exception as e:
        # Unexpected errors
        logger.error(f"Tool execution failed with exception: {e}", exc_info=True)
        return ToolCallResponse(
            name=request.name, result=None, error=f"Tool execution failed: {e}"
        )


async def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    search_engine: HybridSearchEngine,
    resource_service: ResourceService,
    terraform_service: TerraformService,
    git_service: GitService,
) -> Any:
    """Execute a tool and return results.

    Args:
        name: Tool name
        arguments: Tool arguments
        search_engine: Search engine instance
        resource_service: Resource service instance
        terraform_service: Terraform service instance
        git_service: Git service instance

    Returns:
        Tool execution result

    Raises:
        ValueError: If tool execution fails due to invalid input or missing data
        Exception: If tool execution fails unexpectedly
    """
    if name == "search_infrastructure":
        results = await search_engine.search(
            query=arguments["query"],
            mode="hybrid",
            doc_types=arguments.get("doc_types"),
            filters=arguments.get("filters"),
            top=arguments.get("top", 10),
        )
        return {
            "results": [
                {
                    "id": r.id,
                    "content": r.content[:500],  # Truncate for LLM context
                    "doc_type": r.doc_type,
                    "score": r.score,
                    "metadata": r.metadata,
                }
                for r in results.results
            ],
            "total_count": results.total_count,
        }

    elif name == "get_resource_details":
        resource = await resource_service.get_resource(arguments["resource_id"])
        if not resource:
            raise ValueError(f"Resource not found: {arguments['resource_id']}")
        return resource.model_dump()

    elif name == "get_resource_terraform":
        terraform_links = await resource_service.get_terraform_for_resource(
            arguments["resource_id"]
        )
        return [t.model_dump() for t in terraform_links]

    elif name == "get_resource_dependencies":
        deps = await resource_service.get_dependencies(
            arguments["resource_id"],
            direction=arguments.get("direction", "both"),
            depth=arguments.get("depth", 2),
        )
        return [d.model_dump() for d in deps]

    elif name == "query_resource_graph":
        results = await resource_service.execute_resource_graph_query(
            query=arguments["query"],
            subscriptions=arguments.get("subscriptions"),
        )
        return {"results": results}

    elif name == "list_terraform_resources":
        resources = await terraform_service.list_resources(
            repo_url=arguments.get("repo_url"),
            resource_type=arguments.get("type"),
            file_path=arguments.get("file_path"),
            limit=arguments.get("limit", 50),
        )
        return [r.model_dump() for r in resources]

    elif name == "get_terraform_resource":
        resource = await terraform_service.get_resource(
            arguments["address"], arguments["repo_url"]
        )
        if not resource:
            raise ValueError(
                f"Terraform resource not found: {arguments['address']} in {arguments['repo_url']}"
            )
        return resource.model_dump()

    elif name == "get_terraform_plan":
        plan = await terraform_service.get_plan(arguments["plan_id"])
        if not plan:
            raise ValueError(f"Plan not found: {arguments['plan_id']}")
        return plan.model_dump()

    elif name == "analyze_terraform_plan":
        plan = await terraform_service.get_plan(arguments["plan_id"])
        if not plan:
            raise ValueError(f"Plan not found: {arguments['plan_id']}")
        analysis = await terraform_service.analyze_plan(plan)
        return analysis.model_dump()

    elif name == "get_git_history":
        commits = await git_service.list_commits(
            repo_url=arguments.get("repo_url"),
            author=arguments.get("author"),
            since=arguments.get("since"),
            until=arguments.get("until"),
            terraform_only=arguments.get("terraform_only", False),
            limit=arguments.get("limit", 20),
        )
        return [c.model_dump() for c in commits]

    elif name == "get_commit_details":
        commit = await git_service.get_commit(
            arguments["sha"],
            arguments["repo_url"],
        )
        if not commit:
            raise ValueError(
                f"Commit not found: {arguments['sha']} in {arguments['repo_url']}"
            )
        return commit.model_dump()

    elif name == "list_subscriptions":
        subs = await resource_service.list_subscriptions()
        return {"subscriptions": subs}

    elif name == "get_resource_types_summary":
        summary = await resource_service.get_resource_types_summary(
            subscription_id=arguments.get("subscription_id")
        )
        return {"resource_types": summary}

    else:
        raise ValueError(f"Unknown tool: {name}")
