"""Unit tests for hybrid search engine."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.search.hybrid_search import HybridSearchEngine
from src.search.models import SearchResult


@pytest.fixture
def mock_search_client():
    """Create mock Azure AI Search client."""
    mock_client = Mock()
    mock_client.close = Mock()
    return mock_client


@pytest.fixture
def mock_graph_builder():
    """Create mock graph builder."""
    mock_builder = Mock()
    return mock_builder


@pytest.fixture
def mock_embedding_pipeline():
    """Create mock embedding pipeline."""
    mock_pipeline = AsyncMock()
    mock_pipeline.embed_single = AsyncMock(return_value=[0.1] * 1536)
    return mock_pipeline


@pytest.fixture
def search_engine(mock_search_client, mock_graph_builder, mock_embedding_pipeline):
    """Create test search engine."""
    return HybridSearchEngine(
        search_client=mock_search_client,
        graph_builder=mock_graph_builder,
        embedding_pipeline=mock_embedding_pipeline,
    )


class TestHybridSearchEngine:
    """Test suite for HybridSearchEngine."""

    def test_init(self, mock_search_client, mock_graph_builder, mock_embedding_pipeline):
        """Test search engine initialization."""
        engine = HybridSearchEngine(
            search_client=mock_search_client,
            graph_builder=mock_graph_builder,
            embedding_pipeline=mock_embedding_pipeline,
        )

        assert engine.search_client == mock_search_client
        assert engine.graph_builder == mock_graph_builder
        assert engine.embedding_pipeline == mock_embedding_pipeline

    @pytest.mark.asyncio
    async def test_search_hybrid_mode(self, search_engine, mock_search_client, mock_embedding_pipeline):
        """Test hybrid search mode."""
        # Mock search results
        mock_result = {
            "id": "doc-1",
            "@search.score": 0.95,
            "content": "Test content",
            "doc_type": "azure_resource",
            "resource_type": "Microsoft.Compute/virtualMachines",
        }
        mock_search_client.search = Mock(return_value=[mock_result])

        results = await search_engine.search(
            query="find virtual machines",
            mode="hybrid",
            top=10,
        )

        assert len(results.results) == 1
        assert results.results[0].id == "doc-1"
        assert results.results[0].score == 0.95
        mock_embedding_pipeline.embed_single.assert_called_once()
        mock_search_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_vector_mode(self, search_engine, mock_search_client, mock_embedding_pipeline):
        """Test vector search mode."""
        mock_result = {
            "id": "doc-1",
            "@search.score": 0.88,
            "content": "Test content",
            "doc_type": "terraform_resource",
        }
        mock_search_client.search = Mock(return_value=[mock_result])

        results = await search_engine.search(
            query="terraform resources",
            mode="vector",
            top=5,
        )

        assert len(results.results) == 1
        mock_embedding_pipeline.embed_single.assert_called_once_with("terraform resources")

        # Check that search was called with vector query
        call_args = mock_search_client.search.call_args
        assert call_args.kwargs["search_text"] is None
        assert "vector_queries" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_search_keyword_mode(self, search_engine, mock_search_client):
        """Test keyword search mode."""
        mock_result = {
            "id": "doc-1",
            "@search.score": 0.75,
            "content": "Test content",
            "doc_type": "git_commit",
            "@search.highlights": {"content": ["Test <em>content</em>"]},
        }
        mock_search_client.search = Mock(return_value=[mock_result])

        results = await search_engine.search(
            query="test search",
            mode="keyword",
            top=10,
        )

        assert len(results.results) == 1
        assert results.results[0].highlights == ["Test <em>content</em>"]

        # Check that search was called without vector query
        call_args = mock_search_client.search.call_args
        assert call_args.kwargs["search_text"] == "test search"
        assert call_args.kwargs["query_type"] == "semantic"

    @pytest.mark.asyncio
    async def test_search_invalid_mode(self, search_engine):
        """Test that invalid search mode raises error."""
        with pytest.raises(ValueError, match="Invalid search mode"):
            await search_engine.search(query="test", mode="invalid")

    @pytest.mark.asyncio
    async def test_search_with_doc_type_filter(self, search_engine, mock_search_client, mock_embedding_pipeline):
        """Test search with document type filtering."""
        mock_search_client.search = Mock(return_value=[])

        await search_engine.search(
            query="test",
            mode="hybrid",
            doc_types=["azure_resource", "terraform_resource"],
        )

        call_args = mock_search_client.search.call_args
        filter_expr = call_args.kwargs["filter"]
        assert "doc_type eq 'azure_resource'" in filter_expr
        assert "doc_type eq 'terraform_resource'" in filter_expr
        assert " or " in filter_expr

    @pytest.mark.asyncio
    async def test_search_with_custom_filters(self, search_engine, mock_search_client, mock_embedding_pipeline):
        """Test search with custom filters."""
        mock_search_client.search = Mock(return_value=[])

        await search_engine.search(
            query="test",
            mode="hybrid",
            filters={
                "location": "canadaeast",
                "resource_type": "Microsoft.Compute/virtualMachines",
            },
        )

        call_args = mock_search_client.search.call_args
        filter_expr = call_args.kwargs["filter"]
        assert "location eq 'canadaeast'" in filter_expr
        assert "resource_type eq 'Microsoft.Compute/virtualMachines'" in filter_expr

    @pytest.mark.asyncio
    async def test_search_with_facets(self, search_engine, mock_search_client, mock_embedding_pipeline):
        """Test search with facets."""
        mock_result_iter = Mock()
        mock_result_iter.__iter__ = Mock(return_value=iter([]))
        mock_result_iter.get_facets = Mock(
            return_value={
                "doc_type": [{"value": "azure_resource", "count": 10}],
                "location": [{"value": "canadaeast", "count": 5}],
            }
        )
        mock_result_iter.get_count = Mock(return_value=0)
        mock_search_client.search = Mock(return_value=mock_result_iter)

        results = await search_engine.search(
            query="test",
            mode="hybrid",
            include_facets=True,
        )

        assert results.facets is not None
        assert "doc_type" in results.facets

    def test_build_filter_doc_types(self, search_engine):
        """Test building filter for document types."""
        filter_expr = search_engine._build_filter(
            doc_types=["azure_resource", "terraform_resource"],
            filters=None,
        )

        assert "doc_type eq 'azure_resource'" in filter_expr
        assert "doc_type eq 'terraform_resource'" in filter_expr
        assert " or " in filter_expr

    def test_build_filter_list_values(self, search_engine):
        """Test building filter with list values."""
        filter_expr = search_engine._build_filter(
            doc_types=None,
            filters={"location": ["canadaeast", "canadacentral"]},
        )

        assert "location eq 'canadaeast'" in filter_expr
        assert "location eq 'canadacentral'" in filter_expr
        assert " or " in filter_expr

    def test_build_filter_boolean(self, search_engine):
        """Test building filter with boolean values."""
        filter_expr = search_engine._build_filter(
            doc_types=None,
            filters={"has_terraform_changes": True},
        )

        assert "has_terraform_changes eq true" in filter_expr

    def test_build_filter_none_value(self, search_engine):
        """Test building filter with None value."""
        filter_expr = search_engine._build_filter(
            doc_types=None,
            filters={"azure_resource_id": None},
        )

        assert "azure_resource_id eq null" in filter_expr

    def test_build_filter_combined(self, search_engine):
        """Test building filter with multiple conditions."""
        filter_expr = search_engine._build_filter(
            doc_types=["azure_resource"],
            filters={"location": "canadaeast", "has_terraform_changes": False},
        )

        assert "doc_type eq 'azure_resource'" in filter_expr
        assert "location eq 'canadaeast'" in filter_expr
        assert "has_terraform_changes eq false" in filter_expr
        assert " and " in filter_expr

    def test_build_filter_no_filters(self, search_engine):
        """Test building filter with no filters."""
        filter_expr = search_engine._build_filter(doc_types=None, filters=None)

        assert filter_expr is None

    def test_process_results(self, search_engine):
        """Test processing search results."""
        mock_results = [
            {
                "id": "doc-1",
                "@search.score": 0.95,
                "content": "Test content 1",
                "doc_type": "azure_resource",
                "resource_type": "Microsoft.Compute/virtualMachines",
                "location": "canadaeast",
            },
            {
                "id": "doc-2",
                "@search.score": 0.85,
                "content": "Test content 2",
                "doc_type": "terraform_resource",
                "file_path": "main.tf",
            },
        ]

        # Mock result iterator
        mock_result_iter = Mock()
        mock_result_iter.__iter__ = Mock(return_value=iter(mock_results))
        mock_result_iter.get_count = Mock(return_value=2)

        results = search_engine._process_results(mock_result_iter, include_facets=False)

        assert len(results.results) == 2
        assert results.total_count == 2
        assert results.results[0].id == "doc-1"
        assert results.results[0].metadata["resource_type"] == "Microsoft.Compute/virtualMachines"
        assert results.results[1].metadata["file_path"] == "main.tf"

    def test_process_results_with_highlights(self, search_engine):
        """Test processing results with highlights."""
        mock_results = [
            {
                "id": "doc-1",
                "@search.score": 0.95,
                "content": "Test content",
                "doc_type": "azure_resource",
                "@search.highlights": {"content": ["Test <em>content</em>"]},
            }
        ]

        mock_result_iter = Mock()
        mock_result_iter.__iter__ = Mock(return_value=iter(mock_results))
        mock_result_iter.get_count = Mock(return_value=1)

        results = search_engine._process_results(mock_result_iter, include_facets=False)

        assert results.results[0].highlights == ["Test <em>content</em>"]

    @pytest.mark.asyncio
    async def test_search_with_graph_expansion(
        self, search_engine, mock_search_client, mock_graph_builder, mock_embedding_pipeline
    ):
        """Test search with graph expansion."""
        # Mock initial search results
        initial_result = {
            "id": "doc-1",
            "@search.score": 0.95,
            "content": "VM content",
            "doc_type": "azure_resource",
            "resource_id": "/subscriptions/sub-1/.../vm-1",
        }

        # Mock expanded search results
        expanded_result = {
            "id": "doc-2",
            "content": "VNET content",
            "doc_type": "azure_resource",
            "resource_id": "/subscriptions/sub-1/.../vnet-1",
        }

        # First call returns initial results, second call returns expanded results
        mock_search_client.search = Mock(side_effect=[[initial_result], [expanded_result]])

        # Mock graph traversal
        mock_graph_builder.find_dependencies = Mock(
            return_value=[
                [{"id": "/subscriptions/sub-1/.../vnet-1"}]  # Related resource
            ]
        )

        results = await search_engine.search_with_graph_expansion(
            query="find VM",
            top=10,
            expand_depth=1,
        )

        # Should have both initial and expanded results
        assert len(results.results) >= 1
        mock_graph_builder.find_dependencies.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_graph_expansion_no_results(
        self, search_engine, mock_search_client, mock_embedding_pipeline
    ):
        """Test graph expansion with no initial results."""
        mock_search_client.search = Mock(return_value=[])

        results = await search_engine.search_with_graph_expansion(
            query="nonexistent",
            top=10,
        )

        assert len(results.results) == 0

    @pytest.mark.asyncio
    async def test_search_with_graph_expansion_error(
        self, search_engine, mock_search_client, mock_graph_builder, mock_embedding_pipeline
    ):
        """Test graph expansion handles errors gracefully."""
        initial_result = {
            "id": "doc-1",
            "@search.score": 0.95,
            "content": "VM content",
            "doc_type": "azure_resource",
            "resource_id": "/subscriptions/sub-1/.../vm-1",
        }
        mock_search_client.search = Mock(return_value=[initial_result])

        # Mock graph error
        mock_graph_builder.find_dependencies = Mock(side_effect=Exception("Graph error"))

        # Should not raise, just log warning
        results = await search_engine.search_with_graph_expansion(
            query="find VM",
            top=10,
        )

        assert len(results.results) == 1  # Original result still returned

    def test_close(self, search_engine, mock_search_client):
        """Test closing the search engine."""
        search_engine.close()

        mock_search_client.close.assert_called_once()


class TestSearchResultModels:
    """Test suite for search result data models."""

    def test_search_result_creation(self):
        """Test creating a SearchResult."""
        result = SearchResult(
            id="doc-1",
            score=0.95,
            content="Test content",
            doc_type="azure_resource",
            metadata={"location": "canadaeast"},
            highlights=["Test <em>content</em>"],
        )

        assert result.id == "doc-1"
        assert result.score == 0.95
        assert result.doc_type == "azure_resource"
        assert result.metadata["location"] == "canadaeast"
        assert result.highlights[0] == "Test <em>content</em>"

    def test_search_result_str(self):
        """Test SearchResult string representation."""
        result = SearchResult(
            id="doc-1",
            score=0.95,
            content="Test content",
            doc_type="azure_resource",
        )

        str_repr = str(result)
        assert "doc-1" in str_repr
        assert "0.950" in str_repr
        assert "azure_resource" in str_repr

    def test_hybrid_search_results_creation(self):
        """Test creating HybridSearchResults."""
        from src.search.models import HybridSearchResults

        results = HybridSearchResults(
            results=[
                SearchResult(
                    id="doc-1",
                    score=0.95,
                    content="Test",
                    doc_type="azure_resource",
                )
            ],
            total_count=100,
            facets={"doc_type": [{"value": "azure_resource", "count": 50}]},
        )

        assert len(results) == 1
        assert results.total_count == 100
        assert results.facets["doc_type"][0]["count"] == 50

    def test_hybrid_search_results_iteration(self):
        """Test iterating over HybridSearchResults."""
        from src.search.models import HybridSearchResults

        results = HybridSearchResults(
            results=[
                SearchResult(id="doc-1", score=0.95, content="Test 1", doc_type="test"),
                SearchResult(id="doc-2", score=0.85, content="Test 2", doc_type="test"),
            ],
            total_count=2,
        )

        ids = [r.id for r in results]
        assert ids == ["doc-1", "doc-2"]

    def test_hybrid_search_results_indexing(self):
        """Test indexing HybridSearchResults."""
        from src.search.models import HybridSearchResults

        results = HybridSearchResults(
            results=[
                SearchResult(id="doc-1", score=0.95, content="Test 1", doc_type="test"),
                SearchResult(id="doc-2", score=0.85, content="Test 2", doc_type="test"),
            ],
            total_count=2,
        )

        assert results[0].id == "doc-1"
        assert results[1].id == "doc-2"
