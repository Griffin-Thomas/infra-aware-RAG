"""Integration tests for Azure AI Search index management.

These tests require actual Azure AI Search service and will be skipped unless
the AZURE_INTEGRATION_TESTS environment variable is set.

Prerequisites:
- Azure CLI logged in (az login) OR
- Environment variables set:
  - AZURE_SEARCH_ENDPOINT (required)
  - AZURE_SEARCH_KEY (optional, uses DefaultAzureCredential if not set)
- Azure AI Search service deployed in Canada East or Canada Central
"""

import os
from datetime import UTC, datetime

import pytest
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient

from src.indexing.indexer import SearchIndexer
from src.indexing.models import Chunk
from src.indexing.search_index import SearchIndexManager, create_infra_index

# Skip all tests unless integration tests are enabled
pytestmark = pytest.mark.skipif(
    not os.getenv("AZURE_INTEGRATION_TESTS"),
    reason="Integration tests disabled. Set AZURE_INTEGRATION_TESTS=1 to enable.",
)


@pytest.fixture
def search_endpoint():
    """Get Azure AI Search endpoint from environment."""
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    if not endpoint:
        pytest.skip("AZURE_SEARCH_ENDPOINT not set")
    return endpoint


@pytest.fixture
def search_credential(search_endpoint):
    """Create Azure credential for search."""
    api_key = os.getenv("AZURE_SEARCH_KEY")
    if api_key:
        return AzureKeyCredential(api_key)
    else:
        return DefaultAzureCredential()


@pytest.fixture
def test_index_name():
    """Generate unique test index name."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"test-infra-index-{timestamp}"


@pytest.fixture
def index_client(search_endpoint, search_credential):
    """Create SearchIndexClient."""
    return SearchIndexClient(endpoint=search_endpoint, credential=search_credential)


@pytest.fixture
def index_manager(search_endpoint, search_credential, test_index_name):
    """Create SearchIndexManager for testing."""
    manager = SearchIndexManager(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )
    yield manager
    # Cleanup: delete test index after test
    try:
        manager.delete_index()
        print(f"Cleaned up test index: {test_index_name}")
    except Exception as e:
        print(f"Failed to cleanup index: {e}")


@pytest.mark.integration
def test_create_infra_index_schema():
    """Test that index schema can be created."""
    index = create_infra_index(index_name="test-index", embedding_dimensions=1536)

    assert index.name == "test-index"
    assert len(index.fields) == 23  # Verify all fields are present

    # Check key fields
    field_names = {f.name for f in index.fields}
    assert "id" in field_names
    assert "content" in field_names
    assert "doc_type" in field_names
    assert "embedding" in field_names

    # Check vector search is configured
    assert index.vector_search is not None
    assert len(index.vector_search.profiles) == 1
    assert index.vector_search.profiles[0].name == "embedding-profile"

    # Check semantic search is configured
    assert index.semantic_search is not None
    assert len(index.semantic_search.configurations) == 1

    print("Index schema created successfully")
    print(f"  Fields: {len(index.fields)}")
    print(f"  Vector search profiles: {len(index.vector_search.profiles)}")


@pytest.mark.integration
def test_search_index_manager_create_index(index_manager, test_index_name):
    """Test creating index on real Azure AI Search service."""
    # Create index
    index_manager.create_index()

    # Verify it exists
    assert index_manager.index_exists()
    print(f"Successfully created index: {test_index_name}")

    # Get stats
    stats = index_manager.get_index_stats()
    assert stats["document_count"] == 0
    assert stats["storage_size"] >= 0
    print(f"Index stats: {stats}")


@pytest.mark.integration
def test_search_index_manager_update_index(index_manager, test_index_name):
    """Test updating an existing index."""
    # Create initial index
    index_manager.create_index()

    # Update should work (idempotent)
    index_manager.create_index()

    assert index_manager.index_exists()
    print(f"Successfully updated index: {test_index_name}")


@pytest.mark.integration
def test_search_indexer_upload_documents(search_endpoint, test_index_name):
    """Test uploading documents to real search index."""
    # Create index first
    manager = SearchIndexManager(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )
    manager.create_index()

    # Create indexer
    indexer = SearchIndexer(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
        batch_size=10,
    )

    # Create test chunks
    chunks = [
        Chunk(
            chunk_id=f"test-chunk-{i}",
            doc_id=f"test-doc-{i}",
            doc_type="azure_resource",
            text=f"Test content {i}",
            heading=f"Test Heading {i}",
            chunk_index=0,
            total_chunks=1,
            embedding=[0.1] * 1536,
            embedding_model="text-embedding-3-large",
        )
        for i in range(5)
    ]

    # Index chunks
    stats = indexer.index_chunks(iter(chunks))

    assert stats["total"] == 5
    assert stats["succeeded"] == 5
    assert stats["failed"] == 0
    print(f"Successfully indexed {stats['succeeded']} documents")

    # Cleanup
    manager.delete_index()


@pytest.mark.integration
def test_search_indexer_batch_processing(search_endpoint, test_index_name):
    """Test batch processing with multiple batches."""
    # Create index
    manager = SearchIndexManager(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )
    manager.create_index()

    # Create indexer with small batch size
    indexer = SearchIndexer(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
        batch_size=3,  # Small batch to test multiple batches
    )

    # Create 10 test chunks (will need 4 batches with batch_size=3)
    chunks = [
        Chunk(
            chunk_id=f"batch-test-{i}",
            doc_id=f"test-doc-{i}",
            doc_type="terraform_resource",
            text=f"Batch test content {i}",
            chunk_index=0,
            total_chunks=1,
            embedding=[0.2] * 1536,
            embedding_model="text-embedding-3-large",
        )
        for i in range(10)
    ]

    # Index chunks
    stats = indexer.index_chunks(iter(chunks))

    assert stats["total"] == 10
    assert stats["succeeded"] == 10
    assert stats["failed"] == 0
    print(f"Successfully batch indexed {stats['succeeded']} documents in multiple batches")

    # Cleanup
    manager.delete_index()


@pytest.mark.integration
def test_search_indexer_delete_documents(search_endpoint, test_index_name):
    """Test deleting documents from index."""
    # Create index
    manager = SearchIndexManager(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )
    manager.create_index()

    # Create and index test chunks
    indexer = SearchIndexer(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )

    chunks = [
        Chunk(
            chunk_id=f"delete-test-{i}",
            doc_id=f"test-doc-{i}",
            doc_type="git_commit",
            text=f"Delete test content {i}",
            chunk_index=0,
            total_chunks=1,
            embedding=[0.3] * 1536,
            embedding_model="text-embedding-3-large",
        )
        for i in range(3)
    ]

    indexer.index_chunks(iter(chunks))

    # Delete documents
    doc_ids = ["delete-test-0", "delete-test-1"]
    indexer.delete_documents(doc_ids)

    print(f"Successfully deleted {len(doc_ids)} documents")

    # Cleanup
    manager.delete_index()


@pytest.mark.integration
def test_search_query_documents(search_endpoint, test_index_name):
    """Test querying indexed documents."""
    # Create index
    manager = SearchIndexManager(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )
    manager.create_index()

    # Index some documents
    indexer = SearchIndexer(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )

    chunks = [
        Chunk(
            chunk_id=f"query-test-{i}",
            doc_id=f"test-doc-{i}",
            doc_type="azure_resource",
            text=f"Virtual machine configuration {i}",
            chunk_index=0,
            total_chunks=1,
            embedding=[0.4] * 1536,
            embedding_model="text-embedding-3-large",
        )
        for i in range(5)
    ]

    indexer.index_chunks(iter(chunks))

    # Wait a bit for indexing to complete
    import time
    time.sleep(2)

    # Query documents
    search_client = indexer.search_client
    results = search_client.search(search_text="virtual machine", top=10)

    result_list = list(results)
    assert len(result_list) > 0, "Expected to find indexed documents"
    print(f"Found {len(result_list)} documents matching 'virtual machine'")

    # Cleanup
    manager.delete_index()


@pytest.mark.integration
@pytest.mark.slow
def test_large_batch_upload(search_endpoint, test_index_name):
    """Test uploading a large batch of documents."""
    # Create index
    manager = SearchIndexManager(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
    )
    manager.create_index()

    # Create indexer
    indexer = SearchIndexer(
        endpoint=search_endpoint,
        api_key=os.getenv("AZURE_SEARCH_KEY"),
        index_name=test_index_name,
        batch_size=100,
    )

    # Create 500 test chunks
    chunks = [
        Chunk(
            chunk_id=f"large-batch-{i}",
            doc_id=f"test-doc-{i // 10}",
            doc_type="terraform_state",
            text=f"Large batch test content {i}",
            chunk_index=i % 10,
            total_chunks=10,
            embedding=[0.5] * 1536,
            embedding_model="text-embedding-3-large",
        )
        for i in range(500)
    ]

    # Index chunks
    stats = indexer.index_chunks(iter(chunks))

    assert stats["total"] == 500
    assert stats["succeeded"] == 500
    assert stats["failed"] == 0
    print(f"Successfully indexed {stats['succeeded']} documents in large batch test")

    # Cleanup
    manager.delete_index()
