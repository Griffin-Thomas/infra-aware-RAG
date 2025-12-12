"""Unit tests for the CLI tool.

Tests the CLI commands, argument parsing, and output formatting.
"""

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import (
    app,
    get_api_base_url,
    get_headers,
    get_token,
    DEFAULT_API_BASE_URL,
)

runner = CliRunner()


class TestConfiguration:
    """Tests for configuration helpers."""

    def test_get_api_base_url_default(self):
        """Should return default URL when env var not set."""
        import os
        original = os.environ.pop("INFRA_RAG_API_URL", None)
        try:
            url = get_api_base_url()
            assert url == DEFAULT_API_BASE_URL
        finally:
            if original:
                os.environ["INFRA_RAG_API_URL"] = original

    def test_get_api_base_url_from_env(self):
        """Should return URL from environment variable."""
        with patch.dict("os.environ", {"INFRA_RAG_API_URL": "https://custom.api.com/v1"}):
            url = get_api_base_url()
            assert url == "https://custom.api.com/v1"

    def test_get_headers_with_token(self):
        """Should include Authorization header when token provided."""
        headers = get_headers("test-token")
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer test-token"

    def test_get_headers_without_token(self):
        """Should not include Authorization header when token empty."""
        headers = get_headers("")
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers


class TestGetToken:
    """Tests for Azure CLI token retrieval."""

    @pytest.mark.asyncio
    async def test_get_token_success(self):
        """Should return token when Azure CLI succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test-access-token\n"

        with patch("subprocess.run", return_value=mock_result):
            token = await get_token()
            assert token == "test-access-token"

    @pytest.mark.asyncio
    async def test_get_token_cli_not_logged_in(self):
        """Should return empty string when not logged in."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            token = await get_token()
            assert token == ""

    @pytest.mark.asyncio
    async def test_get_token_cli_not_found(self):
        """Should return empty string when Azure CLI not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            token = await get_token()
            assert token == ""

    @pytest.mark.asyncio
    async def test_get_token_timeout(self):
        """Should return empty string on timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("az", 30)):
            token = await get_token()
            assert token == ""


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_output(self):
        """Should display version information."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Infra-Aware RAG CLI" in result.stdout
        assert "Version" in result.stdout


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_shows_api_url(self):
        """Should display API URL configuration."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = runner.invoke(app, ["config"])
            assert result.exit_code == 0
            assert "API URL" in result.stdout

    def test_config_shows_azure_account(self):
        """Should show Azure account when logged in."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "My Test Subscription\n"

        with patch("subprocess.run", return_value=mock_result):
            result = runner.invoke(app, ["config"])
            assert result.exit_code == 0
            assert "Azure Account" in result.stdout


class TestSearchCommand:
    """Tests for the search command."""

    def test_search_requires_query(self):
        """Should require query argument."""
        result = runner.invoke(app, ["search"])
        assert result.exit_code != 0

    def test_search_accepts_options(self):
        """Should accept all command line options."""
        # Just test help output to verify options are defined
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--type" in result.stdout
        assert "--limit" in result.stdout
        assert "--mode" in result.stdout
        assert "--api-url" in result.stdout


class TestQueryCommand:
    """Tests for the query (Resource Graph) command."""

    def test_query_requires_kql(self):
        """Should require KQL query argument."""
        result = runner.invoke(app, ["query"])
        assert result.exit_code != 0

    def test_query_accepts_options(self):
        """Should accept all command line options."""
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "--subscription" in result.stdout
        assert "--output" in result.stdout
        assert "--api-url" in result.stdout


class TestChatCommand:
    """Tests for the chat command."""

    def test_chat_accepts_query(self):
        """Should accept query argument."""
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "query" in result.stdout.lower()

    def test_chat_accepts_subscription(self):
        """Should accept subscription option."""
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--subscription" in result.stdout

    def test_chat_accepts_api_url(self):
        """Should accept api-url option."""
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--api-url" in result.stdout


class TestHelpOutput:
    """Tests for help output."""

    def test_main_help(self):
        """Should display main help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Infra-Aware RAG CLI" in result.stdout
        assert "chat" in result.stdout
        assert "search" in result.stdout
        assert "query" in result.stdout
        assert "version" in result.stdout
        assert "config" in result.stdout

    def test_chat_help(self):
        """Should display chat help."""
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.stdout.lower()
        assert "--subscription" in result.stdout

    def test_search_help(self):
        """Should display search help."""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--type" in result.stdout
        assert "--limit" in result.stdout
        assert "--mode" in result.stdout

    def test_query_help(self):
        """Should display query help."""
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "KQL" in result.stdout or "Kusto" in result.stdout
        assert "--output" in result.stdout

    def test_version_help(self):
        """Should display version help."""
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0

    def test_config_help(self):
        """Should display config help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0


class TestCommandExamples:
    """Tests that verify example commands in docstrings work."""

    def test_search_with_type_option(self):
        """Verify search --type option is properly defined."""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "azure_resource" in result.stdout or "doc_type" in result.stdout.lower()

    def test_query_with_output_option(self):
        """Verify query output options are properly defined."""
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "table" in result.stdout or "json" in result.stdout


class TestAppStructure:
    """Tests for overall app structure and configuration."""

    def test_app_has_name(self):
        """App should have a name."""
        assert app.info.name == "infra-rag"

    def test_app_has_help(self):
        """App should have help text."""
        assert app.info.help is not None
        assert "infrastructure" in app.info.help.lower()

    def test_no_args_shows_help(self):
        """App with no args should show help."""
        result = runner.invoke(app, [])
        # Should show help/usage due to no_args_is_help=True
        # Exit code 2 is the typer standard for missing arguments
        assert result.exit_code in (0, 2)
        assert "Usage" in result.stdout or "chat" in result.stdout


class TestEnvironmentVariables:
    """Tests for environment variable handling."""

    def test_api_url_from_env(self):
        """Should read API URL from environment."""
        with patch.dict("os.environ", {"INFRA_RAG_API_URL": "https://test.api.com"}):
            url = get_api_base_url()
            assert url == "https://test.api.com"

    def test_default_api_url(self):
        """Should use default URL when env var not set."""
        import os
        env_val = os.environ.pop("INFRA_RAG_API_URL", None)
        try:
            url = get_api_base_url()
            assert url == "http://localhost:8000/api/v1"
        finally:
            if env_val:
                os.environ["INFRA_RAG_API_URL"] = env_val
