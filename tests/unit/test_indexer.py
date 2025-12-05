"""Unit tests for Azure AI Search indexer."""

from unittest.mock import Mock, patch

import pytest

from src.indexing.indexer import SearchIndexer
from src.indexing.models import Chunk


@pytest.fixture
def mock_search_client():
    """Create mock search client."""
    mock_client = Mock()
    mock_client.close = Mock()
    return mock_client


@pytest.fixture
def indexer(mock_search_client):
    """Create test indexer."""
    with patch("src.indexing.indexer.SearchClient", return_value=mock_search_client):
        indexer = SearchIndexer(
            endpoint="https://test.search.windows.net",
            api_key="test-key",
            index_name="test-index",
            batch_size=2,
        )
        yield indexer


class TestSearchIndexer:
    """Test suite for SearchIndexer."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch("src.indexing.indexer.SearchClient") as mock_client:
            indexer = SearchIndexer(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                index_name="test-index",
                batch_size=50,
            )

            assert indexer.endpoint == "https://test.search.windows.net"
            assert indexer.index_name == "test-index"
            assert indexer.batch_size == 50
            mock_client.assert_called_once()

    def test_init_with_default_credential(self):
        """Test initialization with DefaultAzureCredential."""
        with patch("src.indexing.indexer.DefaultAzureCredential") as mock_cred:
            with patch("src.indexing.indexer.SearchClient") as mock_client:
                indexer = SearchIndexer(
                    endpoint="https://test.search.windows.net",
                    api_key=None,
                )

                assert indexer.search_client is not None
                mock_cred.assert_called_once()

    def test_index_chunks_single_batch(self, indexer, mock_search_client):
        """Test indexing chunks that fit in one batch."""
        # Mock successful upload
        mock_result = Mock()
        mock_result.succeeded = True
        mock_result.key = "chunk-1"
        mock_search_client.upload_documents = Mock(return_value=[mock_result])

        chunks = [
            Chunk(
                chunk_id="chunk-1",
                doc_id="doc-1",
                doc_type="test",
                text="Test chunk",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        stats = indexer.index_chunks(iter(chunks))

        assert stats["total"] == 1
        assert stats["succeeded"] == 1
        assert stats["failed"] == 0
        assert len(stats["errors"]) == 0
        mock_search_client.upload_documents.assert_called_once()

    def test_index_chunks_multiple_batches(self, indexer, mock_search_client):
        """Test indexing chunks across multiple batches."""
        # Mock successful uploads
        def mock_upload(documents):
            return [Mock(succeeded=True, key=doc["id"]) for doc in documents]

        mock_search_client.upload_documents = mock_upload

        chunks = [
            Chunk(
                chunk_id=f"chunk-{i}",
                doc_id="doc-1",
                doc_type="test",
                text=f"Test chunk {i}",
                chunk_index=i,
                total_chunks=5,
            )
            for i in range(5)
        ]

        stats = indexer.index_chunks(iter(chunks))

        assert stats["total"] == 5
        assert stats["succeeded"] == 5
        assert stats["failed"] == 0

    def test_index_chunks_with_failures(self, indexer, mock_search_client):
        """Test indexing with some failures."""
        # Mock mixed results
        mock_results = [
            Mock(succeeded=True, key="chunk-1"),
            Mock(succeeded=False, key="chunk-2", error_message="Upload failed", status_code=400),
        ]
        mock_search_client.upload_documents = Mock(return_value=mock_results)

        chunks = [
            Chunk(
                chunk_id="chunk-1",
                doc_id="doc-1",
                doc_type="test",
                text="Test chunk 1",
                chunk_index=0,
                total_chunks=2,
            ),
            Chunk(
                chunk_id="chunk-2",
                doc_id="doc-1",
                doc_type="test",
                text="Test chunk 2",
                chunk_index=1,
                total_chunks=2,
            ),
        ]

        stats = indexer.index_chunks(iter(chunks))

        assert stats["total"] == 2
        assert stats["succeeded"] == 1
        assert stats["failed"] == 1
        assert len(stats["errors"]) == 1
        assert stats["errors"][0]["key"] == "chunk-2"

    def test_index_chunks_batch_error(self, indexer, mock_search_client):
        """Test indexing with batch-level error."""
        from azure.core.exceptions import HttpResponseError

        # Mock batch error
        mock_search_client.upload_documents = Mock(
            side_effect=HttpResponseError(message="Batch upload failed")
        )

        chunks = [
            Chunk(
                chunk_id="chunk-1",
                doc_id="doc-1",
                doc_type="test",
                text="Test chunk",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        stats = indexer.index_chunks(iter(chunks))

        assert stats["total"] == 1
        assert stats["succeeded"] == 0
        assert stats["failed"] == 1
        assert len(stats["errors"]) == 1

    def test_index_chunks_empty(self, indexer, mock_search_client):
        """Test indexing empty chunk list."""
        stats = indexer.index_chunks(iter([]))

        assert stats["total"] == 0
        assert stats["succeeded"] == 0
        assert stats["failed"] == 0
        mock_search_client.upload_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_chunks_async(self, indexer, mock_search_client):
        """Test async chunk indexing."""
        # Mock successful upload
        mock_result = Mock()
        mock_result.succeeded = True
        mock_result.key = "chunk-1"
        mock_search_client.upload_documents = Mock(return_value=[mock_result])

        async def async_chunks():
            chunks = [
                Chunk(
                    chunk_id="chunk-1",
                    doc_id="doc-1",
                    doc_type="test",
                    text="Test chunk",
                    chunk_index=0,
                    total_chunks=1,
                ),
            ]
            for chunk in chunks:
                yield chunk

        stats = await indexer.index_chunks_async(async_chunks())

        assert stats["total"] == 1
        assert stats["succeeded"] == 1
        assert stats["failed"] == 0

    def test_delete_documents(self, indexer, mock_search_client):
        """Test deleting documents."""
        # Mock successful deletion
        mock_result = Mock()
        mock_result.succeeded = True
        mock_result.key = "doc-1"
        mock_search_client.delete_documents = Mock(return_value=[mock_result])

        stats = indexer.delete_documents(["doc-1"])

        assert stats["total"] == 1
        assert stats["succeeded"] == 1
        assert stats["failed"] == 0
        mock_search_client.delete_documents.assert_called_once()

    def test_delete_documents_with_failures(self, indexer, mock_search_client):
        """Test deleting documents with failures."""
        # Mock mixed results
        mock_results = [
            Mock(succeeded=True, key="doc-1"),
            Mock(succeeded=False, key="doc-2", error_message="Deletion failed"),
        ]
        mock_search_client.delete_documents = Mock(return_value=mock_results)

        stats = indexer.delete_documents(["doc-1", "doc-2"])

        assert stats["total"] == 2
        assert stats["succeeded"] == 1
        assert stats["failed"] == 1
        assert len(stats["errors"]) == 1

    def test_delete_documents_empty(self, indexer, mock_search_client):
        """Test deleting empty document list."""
        stats = indexer.delete_documents([])

        assert stats["total"] == 0
        assert stats["succeeded"] == 0
        assert stats["failed"] == 0
        mock_search_client.delete_documents.assert_not_called()

    def test_delete_documents_batch_error(self, indexer, mock_search_client):
        """Test deleting documents with batch error."""
        mock_search_client.delete_documents = Mock(side_effect=Exception("Deletion failed"))

        stats = indexer.delete_documents(["doc-1", "doc-2"])

        assert stats["total"] == 2
        assert stats["succeeded"] == 0
        assert stats["failed"] == 2
        assert len(stats["errors"]) == 1

    def test_get_document(self, indexer, mock_search_client):
        """Test retrieving a document."""
        mock_doc = {"id": "doc-1", "content": "Test content"}
        mock_search_client.get_document = Mock(return_value=mock_doc)

        result = indexer.get_document("doc-1")

        assert result == mock_doc
        mock_search_client.get_document.assert_called_once_with(key="doc-1")

    def test_get_document_not_found(self, indexer, mock_search_client):
        """Test retrieving non-existent document."""
        from azure.core.exceptions import HttpResponseError

        mock_error = HttpResponseError(message="Not found")
        mock_error.status_code = 404
        mock_search_client.get_document = Mock(side_effect=mock_error)

        result = indexer.get_document("nonexistent")

        assert result is None

    def test_get_document_error(self, indexer, mock_search_client):
        """Test retrieving document with error."""
        from azure.core.exceptions import HttpResponseError

        mock_error = HttpResponseError(message="Server error")
        mock_error.status_code = 500
        mock_search_client.get_document = Mock(side_effect=mock_error)

        with pytest.raises(HttpResponseError):
            indexer.get_document("doc-1")

    def test_context_manager(self, mock_search_client):
        """Test context manager usage."""
        with patch("src.indexing.indexer.SearchClient", return_value=mock_search_client):
            with SearchIndexer(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
            ) as indexer:
                assert indexer.search_client is not None

            # Client should be closed after exiting context
            mock_search_client.close.assert_called_once()

    def test_close(self, indexer, mock_search_client):
        """Test closing the indexer."""
        indexer.close()

        mock_search_client.close.assert_called_once()


class TestChunkToSearchDocument:
    """Test suite for Chunk.to_search_document() method."""

    def test_basic_conversion(self):
        """Test basic chunk to search document conversion."""
        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="azure_resource",
            text="Test content",
            chunk_index=0,
            total_chunks=1,
        )

        doc = chunk.to_search_document()

        assert doc["id"] == "doc-1:chunk:0"
        assert doc["content"] == "Test content"
        assert doc["doc_type"] == "azure_resource"

    def test_conversion_with_embedding(self):
        """Test conversion with embedding."""
        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="test",
            text="Test content",
            chunk_index=0,
            total_chunks=1,
            embedding=[0.1, 0.2, 0.3],
        )

        doc = chunk.to_search_document()

        assert "embedding" in doc
        assert doc["embedding"] == [0.1, 0.2, 0.3]

    def test_conversion_with_resource_fields(self):
        """Test conversion with resource metadata."""
        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="azure_resource",
            text="Test content",
            chunk_index=0,
            total_chunks=1,
            resource_type="Microsoft.Compute/virtualMachines",
            resource_name="vm-1",
            source_file="resources.json",
        )

        doc = chunk.to_search_document()

        assert doc["resource_type"] == "Microsoft.Compute/virtualMachines"
        assert doc["resource_name"] == "vm-1"
        assert doc["file_path"] == "resources.json"

    def test_conversion_with_tags(self):
        """Test conversion with tags."""
        import json

        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="test",
            text="Test content",
            chunk_index=0,
            total_chunks=1,
            tags={"Environment": "prod", "Owner": "team-a"},
        )

        doc = chunk.to_search_document()

        assert "tags" in doc
        tags = json.loads(doc["tags"])
        assert tags["Environment"] == "prod"
        assert tags["Owner"] == "team-a"

    def test_conversion_with_properties(self):
        """Test conversion with properties."""
        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="azure_resource",
            text="Test content",
            chunk_index=0,
            total_chunks=1,
            properties={
                "subscription_id": "sub-1",
                "resource_group": "rg-1",
                "location": "canadaeast",
                "provider": "azurerm",
            },
        )

        doc = chunk.to_search_document()

        assert doc["subscription_id"] == "sub-1"
        assert doc["resource_group"] == "rg-1"
        assert doc["location"] == "canadaeast"
        assert doc["provider"] == "azurerm"
