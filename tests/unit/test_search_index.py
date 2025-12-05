"""Unit tests for Azure AI Search index management."""

from unittest.mock import Mock, patch

import pytest

from src.indexing.search_index import SearchIndexManager, create_infra_index


class TestCreateInfraIndex:
    """Test suite for create_infra_index function."""

    def test_create_index_default_params(self):
        """Test creating index with default parameters."""
        index = create_infra_index()

        assert index.name == "infra-index"
        assert len(index.fields) > 0

        # Check key fields exist
        field_names = [f.name for f in index.fields]
        assert "id" in field_names
        assert "content" in field_names
        assert "doc_type" in field_names
        assert "embedding" in field_names
        assert "resource_type" in field_names
        assert "provider" in field_names

    def test_create_index_custom_name(self):
        """Test creating index with custom name."""
        index = create_infra_index(index_name="custom-index")

        assert index.name == "custom-index"

    def test_create_index_custom_dimensions(self):
        """Test creating index with custom embedding dimensions."""
        index = create_infra_index(embedding_dimensions=3072)

        # Find embedding field
        embedding_field = next(f for f in index.fields if f.name == "embedding")
        assert embedding_field.vector_search_dimensions == 3072

    def test_vector_search_configuration(self):
        """Test vector search configuration."""
        index = create_infra_index()

        assert index.vector_search is not None
        assert len(index.vector_search.algorithms) > 0
        assert len(index.vector_search.profiles) > 0

        # Check HNSW configuration
        algorithm = index.vector_search.algorithms[0]
        assert algorithm.name == "hnsw-algorithm"

        profile = index.vector_search.profiles[0]
        assert profile.name == "embedding-profile"
        assert profile.algorithm_configuration_name == "hnsw-algorithm"

    def test_semantic_search_configuration(self):
        """Test semantic search configuration."""
        index = create_infra_index()

        assert index.semantic_search is not None
        assert len(index.semantic_search.configurations) > 0

        semantic_config = index.semantic_search.configurations[0]
        assert semantic_config.name == "semantic-config"
        assert len(semantic_config.prioritized_fields.content_fields) > 0

    def test_filterable_fields(self):
        """Test that key fields are filterable."""
        index = create_infra_index()

        filterable_fields = [f.name for f in index.fields if f.filterable]

        # Check important filterable fields
        assert "id" in filterable_fields
        assert "doc_type" in filterable_fields
        assert "resource_type" in filterable_fields
        assert "subscription_id" in filterable_fields
        assert "location" in filterable_fields
        assert "provider" in filterable_fields

    def test_facetable_fields(self):
        """Test that appropriate fields are facetable."""
        index = create_infra_index()

        facetable_fields = [f.name for f in index.fields if f.facetable]

        # Check facetable fields
        assert "doc_type" in facetable_fields
        assert "resource_type" in facetable_fields
        assert "resource_group" in facetable_fields
        assert "provider" in facetable_fields


class TestSearchIndexManager:
    """Test suite for SearchIndexManager."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch("src.indexing.search_index.SearchIndexClient") as mock_client:
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                index_name="test-index",
            )

            assert manager.endpoint == "https://test.search.windows.net"
            assert manager.index_name == "test-index"
            assert manager.embedding_dimensions == 1536
            mock_client.assert_called_once()

    def test_init_with_default_credential(self):
        """Test initialization with DefaultAzureCredential."""
        with patch("src.indexing.search_index.DefaultAzureCredential") as mock_cred:
            with patch("src.indexing.search_index.SearchIndexClient") as mock_client:
                manager = SearchIndexManager(
                    endpoint="https://test.search.windows.net",
                    api_key=None,
                )

                assert manager.index_client is not None
                mock_cred.assert_called_once()

    def test_create_or_update_index(self):
        """Test creating or updating index."""
        mock_client = Mock()
        mock_client.create_or_update_index = Mock(return_value=Mock())

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            )

            result = manager.create_or_update_index()

            assert result is not None
            mock_client.create_or_update_index.assert_called_once()

    def test_create_or_update_index_failure(self):
        """Test index creation failure."""
        mock_client = Mock()
        mock_client.create_or_update_index = Mock(side_effect=Exception("Creation failed"))

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            )

            with pytest.raises(Exception, match="Creation failed"):
                manager.create_or_update_index()

    def test_delete_index(self):
        """Test deleting index."""
        mock_client = Mock()
        mock_client.delete_index = Mock()

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                index_name="test-index",
            )

            manager.delete_index()

            mock_client.delete_index.assert_called_once_with("test-index")

    def test_delete_index_failure(self):
        """Test index deletion failure."""
        mock_client = Mock()
        mock_client.delete_index = Mock(side_effect=Exception("Deletion failed"))

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            )

            with pytest.raises(Exception, match="Deletion failed"):
                manager.delete_index()

    def test_index_exists_true(self):
        """Test checking if index exists (true case)."""
        mock_client = Mock()
        mock_client.get_index = Mock(return_value=Mock())

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            )

            assert manager.index_exists() is True

    def test_index_exists_false(self):
        """Test checking if index exists (false case)."""
        mock_client = Mock()
        mock_client.get_index = Mock(side_effect=Exception("Not found"))

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            )

            assert manager.index_exists() is False

    def test_get_index_stats(self):
        """Test getting index statistics."""
        mock_search_client = Mock()
        mock_results = Mock()
        mock_results.get_count = Mock(return_value=100)
        mock_search_client.search = Mock(return_value=mock_results)

        with patch("src.indexing.search_index.SearchIndexClient"):
            # Patch SearchClient inside the search_index module where it's used
            with patch("azure.search.documents.SearchClient", return_value=mock_search_client):
                manager = SearchIndexManager(
                    endpoint="https://test.search.windows.net",
                    api_key="test-key",
                    index_name="test-index",
                )

                stats = manager.get_index_stats()

                assert stats["index_name"] == "test-index"
                assert stats["document_count"] == 100
                assert stats["exists"] is True

    def test_close(self):
        """Test closing the manager."""
        mock_client = Mock()
        mock_client.close = Mock()

        with patch("src.indexing.search_index.SearchIndexClient", return_value=mock_client):
            manager = SearchIndexManager(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            )

            manager.close()

            mock_client.close.assert_called_once()
