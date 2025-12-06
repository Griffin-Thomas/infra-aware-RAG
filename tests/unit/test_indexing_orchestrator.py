"""Unit tests for indexing orchestrator."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.indexing.models import Chunk
from src.indexing.orchestrator import IndexingOrchestrator, IndexingStats
from src.models.documents import (
    AzureResourceDocument,
    GitCommitDocument,
    TerraformResourceDocument,
)


@pytest.fixture
def mock_cosmos_client():
    """Create mock Cosmos DB client."""
    mock_client = Mock()
    mock_database = Mock()
    mock_container = AsyncMock()

    mock_client.get_database_client.return_value = mock_database
    mock_database.get_container_client.return_value = mock_container

    return mock_client


@pytest.fixture
def mock_search_indexer():
    """Create mock search indexer."""
    mock_indexer = Mock()
    mock_indexer.index_chunks = Mock(
        return_value={"total": 1, "succeeded": 1, "failed": 0, "errors": []}
    )
    return mock_indexer


@pytest.fixture
def mock_embedding_pipeline():
    """Create mock embedding pipeline."""
    mock_pipeline = AsyncMock()

    async def mock_embed_chunks(chunks):
        for chunk in chunks:
            chunk.embedding = [0.1] * 1536
            chunk.embedding_model = "text-embedding-3-large"
            yield chunk

    mock_pipeline.embed_chunks = mock_embed_chunks
    return mock_pipeline


@pytest.fixture
def mock_graph_builder():
    """Create mock graph builder."""
    mock_builder = Mock()
    mock_builder.add_subscription = Mock()
    mock_builder.add_resource_group = Mock()
    mock_builder.add_azure_resource = Mock()
    mock_builder.add_terraform_resource = Mock()
    mock_builder.link_terraform_to_azure = Mock()
    return mock_builder


@pytest.fixture
def orchestrator(
    mock_cosmos_client, mock_search_indexer, mock_embedding_pipeline, mock_graph_builder
):
    """Create test orchestrator."""
    return IndexingOrchestrator(
        cosmos_client=mock_cosmos_client,
        cosmos_database="test-db",
        cosmos_container="test-container",
        search_indexer=mock_search_indexer,
        embedding_pipeline=mock_embedding_pipeline,
        graph_builder=mock_graph_builder,
        batch_size=10,
    )


class TestIndexingStats:
    """Test suite for IndexingStats."""

    def test_init(self):
        """Test stats initialization."""
        stats = IndexingStats()

        assert stats.documents_processed == 0
        assert stats.chunks_created == 0
        assert stats.chunks_embedded == 0
        assert stats.chunks_indexed == 0
        assert stats.graph_vertices_added == 0
        assert stats.graph_edges_added == 0
        assert stats.errors == []
        assert stats.end_time is None

    def test_record_error(self):
        """Test error recording."""
        stats = IndexingStats()
        stats.record_error("doc-1", "Test error")

        assert len(stats.errors) == 1
        assert stats.errors[0]["doc_id"] == "doc-1"
        assert stats.errors[0]["error"] == "Test error"
        assert "timestamp" in stats.errors[0]

    def test_finalize(self):
        """Test finalizing stats."""
        stats = IndexingStats()
        assert stats.end_time is None

        stats.finalize()
        assert stats.end_time is not None

    def test_to_dict(self):
        """Test converting stats to dictionary."""
        stats = IndexingStats()
        stats.documents_processed = 10
        stats.chunks_indexed = 50
        stats.record_error("doc-1", "Test error")
        stats.finalize()

        result = stats.to_dict()

        assert result["documents_processed"] == 10
        assert result["chunks_indexed"] == 50
        assert result["error_count"] == 1
        assert len(result["errors"]) == 1
        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 0


class TestIndexingOrchestrator:
    """Test suite for IndexingOrchestrator."""

    def test_init(self, orchestrator, mock_cosmos_client):
        """Test orchestrator initialization."""
        assert orchestrator.cosmos_database == "test-db"
        assert orchestrator.cosmos_container == "test-container"
        assert orchestrator.batch_size == 10
        assert len(orchestrator.processed_docs) == 0

        # Check that clients were initialized
        mock_cosmos_client.get_database_client.assert_called_once_with("test-db")

    @pytest.mark.asyncio
    async def test_index_azure_resource_document(self, orchestrator, mock_graph_builder):
        """Test indexing an Azure resource document."""
        document = {
            "id": "azure-doc-1",
            "doc_type": "azure_resource",
            "subscription_id": "sub-1",
            "subscription_name": "Production",
            "tenant_id": "tenant-1",
            "resource_group": "rg-test",
            "type": "Microsoft.Compute/virtualMachines",
            "name": "test-vm",
            "location": "canadaeast",
            "properties": {},
            "tags": {},
        }

        stats = await orchestrator.index_document(document)

        assert stats.documents_processed == 1
        assert stats.chunks_created == 1
        assert stats.chunks_embedded == 1
        assert stats.chunks_indexed == 1
        assert stats.graph_vertices_added == 1

        # Verify graph calls
        mock_graph_builder.add_subscription.assert_called_once_with("sub-1", "Production", "tenant-1")
        mock_graph_builder.add_resource_group.assert_called_once()
        mock_graph_builder.add_azure_resource.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_terraform_resource_document(self, orchestrator, mock_graph_builder):
        """Test indexing a Terraform resource document."""
        document = {
            "id": "tf-doc-1",
            "doc_type": "terraform_resource",
            "address": "azurerm_virtual_machine.test",
            "type": "azurerm_virtual_machine",
            "name": "test",
            "file_path": "main.tf",
            "line_number": 10,
            "repo_url": "https://github.com/test/repo",
            "branch": "main",
            "source_code": 'resource "azurerm_virtual_machine" "test" { }',
            "provider": "azurerm",
            "last_commit_sha": "abc123",
            "last_commit_date": datetime.now(UTC).isoformat(),
            "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/test-vm",
        }

        stats = await orchestrator.index_document(document)

        assert stats.documents_processed == 1
        assert stats.chunks_created >= 1
        assert stats.chunks_embedded >= 1

        # Verify graph calls
        mock_graph_builder.add_terraform_resource.assert_called_once()
        mock_graph_builder.link_terraform_to_azure.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_git_commit_document(self, orchestrator):
        """Test indexing a Git commit document."""
        document = {
            "id": "git-doc-1",
            "doc_type": "git_commit",
            "sha": "abc123def456",
            "short_sha": "abc123d",
            "message": "Added new VM",
            "message_subject": "Added new VM",
            "message_body": "",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "committer_name": "Test User",
            "committer_email": "test@example.com",
            "author_date": datetime.now(UTC).isoformat(),
            "commit_date": datetime.now(UTC).isoformat(),
            "repo_url": "https://github.com/test/repo",
            "branch": "main",
            "files_changed": [
                {
                    "path": "main.tf",
                    "change_type": "added",
                    "diff": "+resource \"azurerm_virtual_machine\" \"test\" {}",
                }
            ],
        }

        stats = await orchestrator.index_document(document)

        assert stats.documents_processed == 1
        assert stats.chunks_created >= 1

    @pytest.mark.asyncio
    async def test_index_document_missing_type(self, orchestrator):
        """Test indexing document with missing doc_type."""
        document = {"id": "test-doc"}

        stats = await orchestrator.index_document(document)

        assert stats.documents_processed == 0
        assert len(stats.errors) == 1
        assert "Missing doc_type" in stats.errors[0]["error"]

    @pytest.mark.asyncio
    async def test_index_document_invalid_type(self, orchestrator):
        """Test indexing document with invalid doc_type."""
        document = {"id": "test-doc", "doc_type": "invalid_type"}

        stats = await orchestrator.index_document(document)

        assert stats.chunks_created == 0

    @pytest.mark.asyncio
    async def test_index_documents_batch(self, orchestrator):
        """Test indexing multiple documents."""
        documents = [
            {
                "id": f"azure-doc-{i}",
                "doc_type": "azure_resource",
                "subscription_id": "sub-1",
                "subscription_name": "Production",
                "tenant_id": "tenant-1",
                "resource_group": "rg-test",
                "type": "Microsoft.Compute/virtualMachines",
                "name": f"test-vm-{i}",
                "location": "canadaeast",
                "properties": {},
                "tags": {},
            }
            for i in range(5)
        ]

        stats = await orchestrator.index_documents(documents)

        assert stats.documents_processed == 5
        assert stats.chunks_created == 5
        assert stats.chunks_indexed == 5

    @pytest.mark.asyncio
    async def test_index_all_documents(self, orchestrator, mock_cosmos_client):
        """Test indexing all documents from Cosmos DB."""
        # Mock query results
        mock_items = [
            {
                "id": f"azure-doc-{i}",
                "doc_type": "azure_resource",
                "subscription_id": "sub-1",
                "subscription_name": "Production",
                "tenant_id": "tenant-1",
                "resource_group": "rg-test",
                "type": "Microsoft.Compute/virtualMachines",
                "name": f"test-vm-{i}",
                "location": "canadaeast",
                "properties": {},
                "tags": {},
            }
            for i in range(3)
        ]

        async def mock_query():
            for item in mock_items:
                yield item

        mock_container = orchestrator.container
        mock_container.query_items = Mock(return_value=mock_query())

        stats = await orchestrator.index_all_documents(incremental=False)

        assert stats.documents_processed == 3
        assert stats.chunks_indexed == 3

    @pytest.mark.asyncio
    async def test_index_all_documents_with_filter(self, orchestrator, mock_cosmos_client):
        """Test indexing with document type filter."""
        mock_container = orchestrator.container

        async def mock_query():
            yield {
                "id": "azure-doc-1",
                "doc_type": "azure_resource",
                "subscription_id": "sub-1",
                "subscription_name": "Production",
                "tenant_id": "tenant-1",
                "resource_group": "rg-test",
                "type": "Microsoft.Compute/virtualMachines",
                "name": "test-vm",
                "location": "canadaeast",
                "properties": {},
                "tags": {},
            }

        mock_container.query_items = Mock(return_value=mock_query())

        stats = await orchestrator.index_all_documents(doc_types=["azure_resource"])

        assert stats.documents_processed == 1

        # Verify query was called with filter
        call_args = mock_container.query_items.call_args
        assert "azure_resource" in call_args.kwargs["query"]

    @pytest.mark.asyncio
    async def test_index_all_documents_incremental(self, orchestrator, mock_cosmos_client):
        """Test incremental indexing skips processed documents."""
        mock_items = [
            {
                "id": "doc-1",
                "doc_type": "azure_resource",
                "subscription_id": "sub-1",
                "subscription_name": "Production",
                "tenant_id": "tenant-1",
                "resource_group": "rg-test",
                "type": "Microsoft.Compute/virtualMachines",
                "name": "test-vm",
                "location": "canadaeast",
                "properties": {},
                "tags": {},
            },
            {
                "id": "doc-2",
                "doc_type": "azure_resource",
                "subscription_id": "sub-1",
                "subscription_name": "Production",
                "tenant_id": "tenant-1",
                "resource_group": "rg-test",
                "type": "Microsoft.Storage/storageAccounts",
                "name": "teststorage",
                "location": "canadaeast",
                "properties": {},
                "tags": {},
            },
        ]

        async def mock_query():
            for item in mock_items:
                yield item

        mock_container = orchestrator.container
        mock_container.query_items = Mock(return_value=mock_query())

        # First run - should process both
        stats1 = await orchestrator.index_all_documents(incremental=True)
        assert stats1.documents_processed == 2

        # Second run - should skip both (already processed)
        mock_container.query_items = Mock(return_value=mock_query())
        stats2 = await orchestrator.index_all_documents(incremental=True)
        assert stats2.documents_processed == 0

    def test_reset_processed_docs(self, orchestrator):
        """Test resetting processed documents set."""
        orchestrator.processed_docs.add("doc-1")
        orchestrator.processed_docs.add("doc-2")

        assert orchestrator.get_processed_count() == 2

        orchestrator.reset_processed_docs()

        assert orchestrator.get_processed_count() == 0

    @pytest.mark.asyncio
    async def test_chunk_document_error_handling(self, orchestrator):
        """Test error handling when chunking fails."""
        invalid_document = {
            "id": "invalid-doc",
            "doc_type": "azure_resource",
            # Missing required fields
        }

        chunks = await orchestrator._chunk_document(invalid_document, "azure_resource")

        # Should return empty list on error, not raise
        assert chunks == []

    @pytest.mark.asyncio
    async def test_populate_graph_error_handling(self, orchestrator, mock_graph_builder):
        """Test error handling when graph population fails."""
        mock_graph_builder.add_subscription.side_effect = Exception("Graph error")

        document = {
            "id": "test-doc",
            "doc_type": "azure_resource",
            "subscription_id": "sub-1",
            "subscription_name": "Production",
            "tenant_id": "tenant-1",
            "resource_group": "rg-test",
            "type": "Microsoft.Compute/virtualMachines",
            "name": "test-vm",
            "location": "canadaeast",
        }

        # Should not raise, just log error
        await orchestrator._populate_graph(document, "azure_resource")

    @pytest.mark.asyncio
    async def test_indexing_with_search_indexer_error(self, orchestrator):
        """Test handling of search indexer errors."""
        # Mock indexer to report failures
        orchestrator.indexer.index_chunks = Mock(
            return_value={"total": 1, "succeeded": 0, "failed": 1, "errors": [{"key": "chunk-1", "error": "Upload failed"}]}
        )

        document = {
            "id": "test-doc",
            "doc_type": "azure_resource",
            "subscription_id": "sub-1",
            "subscription_name": "Production",
            "tenant_id": "tenant-1",
            "resource_group": "rg-test",
            "type": "Microsoft.Compute/virtualMachines",
            "name": "test-vm",
            "location": "canadaeast",
            "properties": {},
            "tags": {},
        }

        stats = await orchestrator.index_document(document)

        # Should still process document but record the error
        assert stats.documents_processed == 1
        assert len(stats.errors) > 0
