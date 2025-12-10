"""LLM tool definitions compatible with OpenAI/Anthropic function calling.

This module defines all tools that the LLM can call to interact with
Azure infrastructure, Terraform IaC, and Git history.

Each tool definition includes:
- name: Tool identifier
- description: What the tool does (shown to LLM)
- parameters: JSON Schema for tool parameters
"""

from typing import Any

# All tool definitions in OpenAI/Anthropic function calling format
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_infrastructure",
        "description": """Search across Azure resources, Terraform code, and Git history.
        Use this tool to find resources by name, type, tags, or any other attribute.
        Returns relevant results with metadata and relevance scores.""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "doc_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific document types: azure_resource, terraform_resource, git_commit, terraform_plan",
                },
                "filters": {
                    "type": "object",
                    "description": "Additional filters (e.g., location, resource_group, subscription_id)",
                },
                "top": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_resource_details",
        "description": """Get full details for a specific Azure resource by its ID.
        Use this when you need complete information about a single resource.""",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "The full Azure Resource ID",
                }
            },
            "required": ["resource_id"],
        },
    },
    {
        "name": "get_resource_terraform",
        "description": """Find the Terraform code that manages an Azure resource.
        Returns the Terraform resource definition including file path and source code.""",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "The Azure Resource ID to find Terraform for",
                }
            },
            "required": ["resource_id"],
        },
    },
    {
        "name": "get_resource_dependencies",
        "description": """Get resources that depend on or are depended upon by a given resource.
        Useful for understanding impact of changes.""",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "The Azure Resource ID",
                },
                "direction": {
                    "type": "string",
                    "enum": ["in", "out", "both"],
                    "description": "Direction of dependencies (default: both)",
                },
                "depth": {
                    "type": "integer",
                    "description": "How many levels of dependencies to traverse (default: 2)",
                },
            },
            "required": ["resource_id"],
        },
    },
    {
        "name": "query_resource_graph",
        "description": """Execute a Kusto query against Azure Resource Graph.
        Use this for complex queries that need filtering, aggregation, or joins.
        The query language is Kusto (KQL).""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Kusto query to execute against Resource Graph",
                },
                "subscriptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of subscription IDs to query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_terraform_resources",
        "description": """List Terraform resources with optional filters.
        Use this to discover Terraform resources by type, repository, or file path.""",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_url": {
                    "type": "string",
                    "description": "Filter by repository URL",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by resource type (e.g., 'azurerm_virtual_machine')",
                },
                "file_path": {
                    "type": "string",
                    "description": "Filter by file path",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 50)",
                },
            },
        },
    },
    {
        "name": "get_terraform_resource",
        "description": """Get details for a specific Terraform resource by address.
        Use this to see the full Terraform configuration for a resource.""",
        "parameters": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "The Terraform resource address (e.g., 'azurerm_virtual_machine.example')",
                },
                "repo_url": {
                    "type": "string",
                    "description": "Repository URL",
                },
            },
            "required": ["address", "repo_url"],
        },
    },
    {
        "name": "get_terraform_plan",
        "description": """Get details of a Terraform plan including all planned changes.
        Use this to understand what will happen when a plan is applied.""",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "The plan ID",
                }
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "analyze_terraform_plan",
        "description": """Get AI-generated analysis of a Terraform plan.
        Returns a summary, risk assessment, and recommendations.""",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "The plan ID to analyze",
                }
            },
            "required": ["plan_id"],
        },
    },
    {
        "name": "get_git_history",
        "description": """Get Git commit history for infrastructure changes.
        Use this to understand who changed what and when.""",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_url": {
                    "type": "string",
                    "description": "Repository URL (optional)",
                },
                "author": {
                    "type": "string",
                    "description": "Filter by author name or email",
                },
                "since": {
                    "type": "string",
                    "description": "Start date (ISO format)",
                },
                "until": {
                    "type": "string",
                    "description": "End date (ISO format)",
                },
                "terraform_only": {
                    "type": "boolean",
                    "description": "Only show commits with Terraform changes",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of commits to return (default: 20)",
                },
            },
        },
    },
    {
        "name": "get_commit_details",
        "description": """Get full details for a specific Git commit including diff.""",
        "parameters": {
            "type": "object",
            "properties": {
                "sha": {
                    "type": "string",
                    "description": "The commit SHA",
                },
                "repo_url": {
                    "type": "string",
                    "description": "Repository URL",
                },
            },
            "required": ["sha", "repo_url"],
        },
    },
    {
        "name": "list_subscriptions",
        "description": """List all Azure subscriptions that are being tracked.
        Returns subscription IDs and names.""",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_resource_types_summary",
        "description": """Get a summary of all resource types and their counts.
        Useful for understanding what's in the environment.""",
        "parameters": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "Optional subscription ID to filter",
                }
            },
        },
    },
]


def get_tool_definitions() -> list[dict[str, Any]]:
    """Get all tool definitions.

    Returns:
        List of tool definitions in OpenAI/Anthropic function calling format.
        Each definition includes name, description, and parameter schema.
    """
    return TOOL_DEFINITIONS


def get_tool_by_name(name: str) -> dict[str, Any] | None:
    """Get a specific tool definition by name.

    Args:
        name: Tool name to look up

    Returns:
        Tool definition dict if found, None otherwise.
    """
    for tool in TOOL_DEFINITIONS:
        if tool["name"] == name:
            return tool
    return None


def list_tool_names() -> list[str]:
    """Get a list of all available tool names.

    Returns:
        List of tool names.
    """
    return [tool["name"] for tool in TOOL_DEFINITIONS]


def validate_tool_call(name: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate a tool call against its definition.

    Args:
        name: Tool name
        arguments: Tool arguments to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if tool call is valid
        - error_message: None if valid, error description if invalid
    """
    tool = get_tool_by_name(name)
    if not tool:
        return False, f"Unknown tool: {name}"

    # Check required parameters
    required_params = tool["parameters"].get("required", [])
    for param in required_params:
        if param not in arguments:
            return False, f"Missing required parameter: {param}"

    # Check for unexpected parameters
    allowed_params = set(tool["parameters"]["properties"].keys())
    provided_params = set(arguments.keys())
    unexpected = provided_params - allowed_params
    if unexpected:
        return False, f"Unexpected parameters: {', '.join(unexpected)}"

    return True, None
