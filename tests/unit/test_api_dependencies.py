"""Unit tests for API dependencies and settings."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.dependencies import (
    Settings,
    get_arg_connector,
    get_cosmos_client,
    get_graph_builder,
    get_search_engine,
    get_settings,
    init_services,
    cleanup_services,
    _services,
)


class TestSettings:
    """Tests for Settings configuration."""

    def test_settings_has_required_fields(self):
        """Test that Settings has all required fields."""
        # Create settings with minimal required fields
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "COSMOS_DB_ENDPOINT": "https://test.documents.azure.com",
                "COSMOS_DB_GREMLIN_ENDPOINT": "https://test.documents.azure.com:443/",
                "COSMOS_DB_GREMLIN_KEY": "test-gremlin-key",
            },
        ):
            settings = Settings()

            assert settings.azure_openai_endpoint == "https://test.openai.azure.com"
            assert settings.azure_search_endpoint == "https://test.search.windows.net"
            assert settings.cosmos_db_endpoint == "https://test.documents.azure.com"

    def test_settings_default_values(self):
        """Test that Settings has correct default values."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "COSMOS_DB_ENDPOINT": "https://test.documents.azure.com",
                "COSMOS_DB_GREMLIN_ENDPOINT": "https://test.documents.azure.com:443/",
                "COSMOS_DB_GREMLIN_KEY": "test-gremlin-key",
            },
        ):
            settings = Settings()

            # Check defaults
            assert settings.azure_region == "canadaeast"
            assert settings.azure_search_index_name == "infra-rag-index"
            assert settings.cosmos_db_database == "infra-rag"
            assert settings.cosmos_db_gremlin_graph == "infrastructure"
            assert settings.api_version == "1.0.0"
            assert settings.rate_limit_per_minute == 60
            assert settings.rate_limit_per_hour == 1000

    def test_settings_cors_defaults(self):
        """Test CORS settings defaults."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "COSMOS_DB_ENDPOINT": "https://test.documents.azure.com",
                "COSMOS_DB_GREMLIN_ENDPOINT": "https://test.documents.azure.com:443/",
                "COSMOS_DB_GREMLIN_KEY": "test-gremlin-key",
            },
        ):
            settings = Settings()

            assert settings.cors_origins == ["*"]
            assert settings.cors_allow_credentials is True

    def test_get_settings_caches_instance(self):
        """Test that get_settings returns cached instance."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "COSMOS_DB_ENDPOINT": "https://test.documents.azure.com",
                "COSMOS_DB_GREMLIN_ENDPOINT": "https://test.documents.azure.com:443/",
                "COSMOS_DB_GREMLIN_KEY": "test-gremlin-key",
            },
        ):
            # Clear the cache first
            get_settings.cache_clear()

            settings1 = get_settings()
            settings2 = get_settings()

            # Should be the same instance (cached)
            assert settings1 is settings2


class TestServiceInitialization:
    """Tests for service initialization and cleanup."""

    @pytest.mark.asyncio
    async def test_init_services_creates_clients(self):
        """Test that init_services creates all required clients."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "COSMOS_DB_ENDPOINT": "https://test.documents.azure.com",
                "COSMOS_DB_GREMLIN_ENDPOINT": "https://test.documents.azure.com:443/",
                "COSMOS_DB_GREMLIN_KEY": "test-gremlin-key",
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()

            # Mock all the Azure clients
            with patch(
                "src.api.dependencies.DefaultAzureCredential"
            ) as mock_cred, patch(
                "src.api.dependencies.CosmosClient"
            ) as mock_cosmos, patch(
                "src.api.dependencies.AzureResourceGraphConnector"
            ) as mock_arg, patch(
                "src.api.dependencies.HybridSearchEngine"
            ) as mock_search, patch(
                "src.api.dependencies.GraphBuilder"
            ) as mock_graph:

                await init_services(settings)

                # Verify all services were initialized
                assert "cosmos_client" in _services
                assert "arg_connector" in _services
                assert "search_engine" in _services
                assert "graph_builder" in _services

                # Verify constructors were called
                mock_cosmos.assert_called_once()
                mock_arg.assert_called_once()
                mock_search.assert_called_once()
                mock_graph.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_services_closes_clients(self):
        """Test that cleanup_services closes all clients."""
        # Set up mock services
        mock_cosmos = AsyncMock()
        _services["cosmos_client"] = mock_cosmos
        _services["arg_connector"] = MagicMock()
        _services["search_engine"] = MagicMock()
        _services["graph_builder"] = MagicMock()

        await cleanup_services()

        # Verify cosmos client was closed
        mock_cosmos.close.assert_called_once()

        # Verify services were cleared
        assert len(_services) == 0


class TestDependencyGetters:
    """Tests for dependency getter functions."""

    def test_get_search_engine_raises_when_not_initialized(self):
        """Test that get_search_engine raises error when not initialized."""
        # Clear services
        _services.clear()

        with pytest.raises(RuntimeError, match="Services not initialized"):
            get_search_engine()

    def test_get_search_engine_returns_instance(self):
        """Test that get_search_engine returns correct instance."""
        mock_engine = MagicMock()
        _services["search_engine"] = mock_engine

        result = get_search_engine()

        assert result is mock_engine

    def test_get_graph_builder_raises_when_not_initialized(self):
        """Test that get_graph_builder raises error when not initialized."""
        _services.clear()

        with pytest.raises(RuntimeError, match="Services not initialized"):
            get_graph_builder()

    def test_get_graph_builder_returns_instance(self):
        """Test that get_graph_builder returns correct instance."""
        mock_builder = MagicMock()
        _services["graph_builder"] = mock_builder

        result = get_graph_builder()

        assert result is mock_builder

    def test_get_cosmos_client_raises_when_not_initialized(self):
        """Test that get_cosmos_client raises error when not initialized."""
        _services.clear()

        with pytest.raises(RuntimeError, match="Services not initialized"):
            get_cosmos_client()

    def test_get_cosmos_client_returns_instance(self):
        """Test that get_cosmos_client returns correct instance."""
        mock_client = MagicMock()
        _services["cosmos_client"] = mock_client

        result = get_cosmos_client()

        assert result is mock_client

    def test_get_arg_connector_raises_when_not_initialized(self):
        """Test that get_arg_connector raises error when not initialized."""
        _services.clear()

        with pytest.raises(RuntimeError, match="Services not initialized"):
            get_arg_connector()

    def test_get_arg_connector_returns_instance(self):
        """Test that get_arg_connector returns correct instance."""
        mock_connector = MagicMock()
        _services["arg_connector"] = mock_connector

        result = get_arg_connector()

        assert result is mock_connector


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Cleanup services after each test."""
    yield
    _services.clear()
    get_settings.cache_clear()
