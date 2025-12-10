"""Unit tests for LLM tool definitions."""

import pytest
from src.api.tools.definitions import (
    TOOL_DEFINITIONS,
    get_tool_definitions,
    get_tool_by_name,
    list_tool_names,
    validate_tool_call,
)


class TestToolDefinitions:
    """Tests for tool definitions structure."""

    def test_all_tools_have_required_fields(self):
        """Test that all tools have name, description, and parameters."""
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool missing 'description': {tool.get('name')}"
            assert "parameters" in tool, f"Tool missing 'parameters': {tool.get('name')}"

            # Verify parameters structure
            params = tool["parameters"]
            assert params["type"] == "object", f"Parameters should be object type: {tool['name']}"
            assert "properties" in params, f"Parameters missing 'properties': {tool['name']}"

    def test_tool_names_are_unique(self):
        """Test that all tool names are unique."""
        names = [tool["name"] for tool in TOOL_DEFINITIONS]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_tool_descriptions_are_not_empty(self):
        """Test that all tool descriptions are meaningful."""
        for tool in TOOL_DEFINITIONS:
            assert len(tool["description"].strip()) > 0, f"Empty description: {tool['name']}"
            # Should be at least a sentence
            assert len(tool["description"]) > 20, f"Description too short: {tool['name']}"

    def test_required_parameters_are_in_properties(self):
        """Test that all required parameters are defined in properties."""
        for tool in TOOL_DEFINITIONS:
            required = tool["parameters"].get("required", [])
            properties = tool["parameters"]["properties"]

            for param in required:
                assert param in properties, (
                    f"Required param '{param}' not in properties for tool '{tool['name']}'"
                )

    def test_parameter_descriptions_exist(self):
        """Test that all parameters have descriptions."""
        for tool in TOOL_DEFINITIONS:
            properties = tool["parameters"]["properties"]

            for param_name, param_def in properties.items():
                assert "description" in param_def, (
                    f"Parameter '{param_name}' in tool '{tool['name']}' missing description"
                )
                assert len(param_def["description"]) > 0, (
                    f"Empty description for parameter '{param_name}' in tool '{tool['name']}'"
                )


class TestGetToolDefinitions:
    """Tests for get_tool_definitions function."""

    def test_get_tool_definitions_returns_list(self):
        """Test that get_tool_definitions returns a list."""
        tools = get_tool_definitions()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_get_tool_definitions_returns_same_as_constant(self):
        """Test that get_tool_definitions returns TOOL_DEFINITIONS."""
        assert get_tool_definitions() == TOOL_DEFINITIONS


class TestGetToolByName:
    """Tests for get_tool_by_name function."""

    def test_get_existing_tool(self):
        """Test getting an existing tool by name."""
        tool = get_tool_by_name("search_infrastructure")
        assert tool is not None
        assert tool["name"] == "search_infrastructure"
        assert "description" in tool
        assert "parameters" in tool

    def test_get_nonexistent_tool(self):
        """Test getting a tool that doesn't exist."""
        tool = get_tool_by_name("nonexistent_tool")
        assert tool is None

    def test_get_all_tools_by_name(self):
        """Test that all tools can be retrieved by name."""
        for tool_def in TOOL_DEFINITIONS:
            tool = get_tool_by_name(tool_def["name"])
            assert tool is not None
            assert tool == tool_def


class TestListToolNames:
    """Tests for list_tool_names function."""

    def test_list_tool_names_returns_list(self):
        """Test that list_tool_names returns a list."""
        names = list_tool_names()
        assert isinstance(names, list)
        assert len(names) > 0

    def test_list_tool_names_matches_definitions(self):
        """Test that listed names match TOOL_DEFINITIONS."""
        names = list_tool_names()
        expected_names = [tool["name"] for tool in TOOL_DEFINITIONS]
        assert names == expected_names

    def test_all_names_are_strings(self):
        """Test that all tool names are strings."""
        names = list_tool_names()
        for name in names:
            assert isinstance(name, str)
            assert len(name) > 0


class TestValidateToolCall:
    """Tests for validate_tool_call function."""

    def test_validate_valid_search_call(self):
        """Test validating a valid search_infrastructure call."""
        is_valid, error = validate_tool_call(
            "search_infrastructure",
            {"query": "virtual machines in production"},
        )
        assert is_valid is True
        assert error is None

    def test_validate_search_with_optional_params(self):
        """Test validating search with optional parameters."""
        is_valid, error = validate_tool_call(
            "search_infrastructure",
            {
                "query": "storage accounts",
                "doc_types": ["azure_resource"],
                "top": 10,
            },
        )
        assert is_valid is True
        assert error is None

    def test_validate_missing_required_param(self):
        """Test validating a call missing a required parameter."""
        is_valid, error = validate_tool_call(
            "search_infrastructure",
            {"top": 10},  # Missing required 'query'
        )
        assert is_valid is False
        assert error is not None
        assert "query" in error.lower()

    def test_validate_unknown_tool(self):
        """Test validating a call to an unknown tool."""
        is_valid, error = validate_tool_call(
            "unknown_tool",
            {"param": "value"},
        )
        assert is_valid is False
        assert error is not None
        assert "unknown tool" in error.lower()

    def test_validate_unexpected_parameter(self):
        """Test validating a call with unexpected parameters."""
        is_valid, error = validate_tool_call(
            "get_resource_details",
            {
                "resource_id": "/subscriptions/xxx/resourceGroups/yyy/...",
                "unexpected_param": "value",
            },
        )
        assert is_valid is False
        assert error is not None
        assert "unexpected" in error.lower()

    def test_validate_get_commit_details(self):
        """Test validating get_commit_details call."""
        is_valid, error = validate_tool_call(
            "get_commit_details",
            {
                "sha": "abc123",
                "repo_url": "https://github.com/example/repo",
            },
        )
        assert is_valid is True
        assert error is None

    def test_validate_list_subscriptions_no_params(self):
        """Test validating list_subscriptions with no parameters."""
        is_valid, error = validate_tool_call("list_subscriptions", {})
        assert is_valid is True
        assert error is None


class TestToolCoverage:
    """Tests to verify tool coverage matches API endpoints."""

    def test_search_tools_exist(self):
        """Test that search-related tools exist."""
        names = list_tool_names()
        assert "search_infrastructure" in names

    def test_resource_tools_exist(self):
        """Test that resource-related tools exist."""
        names = list_tool_names()
        assert "get_resource_details" in names
        assert "get_resource_terraform" in names
        assert "get_resource_dependencies" in names
        assert "query_resource_graph" in names
        assert "list_subscriptions" in names
        assert "get_resource_types_summary" in names

    def test_terraform_tools_exist(self):
        """Test that Terraform-related tools exist."""
        names = list_tool_names()
        assert "list_terraform_resources" in names
        assert "get_terraform_resource" in names
        assert "get_terraform_plan" in names
        assert "analyze_terraform_plan" in names

    def test_git_tools_exist(self):
        """Test that Git-related tools exist."""
        names = list_tool_names()
        assert "get_git_history" in names
        assert "get_commit_details" in names

    def test_minimum_tool_count(self):
        """Test that we have a reasonable number of tools."""
        names = list_tool_names()
        # Should have at least 13 tools as defined in the spec
        assert len(names) >= 13


class TestToolParameterTypes:
    """Tests for parameter type definitions."""

    def test_search_infrastructure_parameters(self):
        """Test search_infrastructure parameter types."""
        tool = get_tool_by_name("search_infrastructure")
        props = tool["parameters"]["properties"]

        assert props["query"]["type"] == "string"
        assert props["doc_types"]["type"] == "array"
        assert props["filters"]["type"] == "object"
        assert props["top"]["type"] == "integer"

    def test_get_resource_details_parameters(self):
        """Test get_resource_details parameter types."""
        tool = get_tool_by_name("get_resource_details")
        props = tool["parameters"]["properties"]

        assert props["resource_id"]["type"] == "string"
        assert "resource_id" in tool["parameters"]["required"]

    def test_get_resource_dependencies_parameters(self):
        """Test get_resource_dependencies parameter types."""
        tool = get_tool_by_name("get_resource_dependencies")
        props = tool["parameters"]["properties"]

        assert props["resource_id"]["type"] == "string"
        assert props["direction"]["type"] == "string"
        assert props["direction"]["enum"] == ["in", "out", "both"]
        assert props["depth"]["type"] == "integer"

    def test_get_git_history_parameters(self):
        """Test get_git_history parameter types."""
        tool = get_tool_by_name("get_git_history")
        props = tool["parameters"]["properties"]

        assert props["repo_url"]["type"] == "string"
        assert props["author"]["type"] == "string"
        assert props["since"]["type"] == "string"
        assert props["until"]["type"] == "string"
        assert props["terraform_only"]["type"] == "boolean"
        assert props["limit"]["type"] == "integer"
