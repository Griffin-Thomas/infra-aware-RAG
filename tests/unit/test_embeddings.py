"""Unit tests for embedding pipeline."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.indexing.embeddings import EmbeddingPipeline
from src.indexing.models import Chunk


@pytest.fixture
def mock_openai_client():
    """Create mock OpenAI client."""
    mock_client = AsyncMock()

    # Mock embeddings.create response
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1] * 1536),
        Mock(embedding=[0.2] * 1536),
    ]
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)
    mock_client.close = AsyncMock()

    return mock_client


@pytest.fixture
async def pipeline(mock_openai_client):
    """Create test pipeline."""
    with patch("src.indexing.embeddings.AsyncAzureOpenAI", return_value=mock_openai_client):
        pipeline = EmbeddingPipeline(
            azure_endpoint="https://test.openai.azure.com",
            api_key="test-key",
            batch_size=2,
        )
        await pipeline._initialize_client()
        yield pipeline
        await pipeline.close()


class TestEmbeddingPipeline:
    """Test suite for EmbeddingPipeline."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Test pipeline initialization."""
        pipeline = EmbeddingPipeline(
            azure_endpoint="https://test.openai.azure.com",
            api_key="test-key",
            dimensions=1536,
            batch_size=16,
        )

        assert pipeline.azure_endpoint == "https://test.openai.azure.com"
        assert pipeline.model == "text-embedding-3-large"
        assert pipeline.dimensions == 1536
        assert pipeline.batch_size == 16
        assert pipeline.max_retries == 3
        assert pipeline.encoding is not None

    @pytest.mark.asyncio
    async def test_embed_single(self, pipeline, mock_openai_client):
        """Test embedding a single text."""
        text = "Test text for embedding"

        embedding = await pipeline.embed_single(text)

        assert len(embedding) == 1536
        assert embedding == [0.1] * 1536
        mock_openai_client.embeddings.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_chunks(self, pipeline, mock_openai_client):
        """Test embedding multiple chunks."""
        chunks = [
            Chunk(
                chunk_id="doc-1:chunk:0",
                doc_id="doc-1",
                doc_type="test",
                text="First chunk text",
                chunk_index=0,
                total_chunks=2,
            ),
            Chunk(
                chunk_id="doc-1:chunk:1",
                doc_id="doc-1",
                doc_type="test",
                text="Second chunk text",
                chunk_index=1,
                total_chunks=2,
            ),
        ]

        result_chunks = []
        async for chunk in pipeline.embed_chunks(chunks):
            result_chunks.append(chunk)

        assert len(result_chunks) == 2
        assert result_chunks[0].embedding == [0.1] * 1536
        assert result_chunks[0].embedding_model == "text-embedding-3-large"
        assert result_chunks[0].token_count is not None
        assert result_chunks[1].embedding == [0.2] * 1536

    @pytest.mark.asyncio
    async def test_embed_chunks_batching(self, pipeline, mock_openai_client):
        """Test that chunks are processed in batches."""
        # Create 5 chunks with batch_size=2
        chunks = [
            Chunk(
                chunk_id=f"doc-1:chunk:{i}",
                doc_id="doc-1",
                doc_type="test",
                text=f"Chunk {i} text",
                chunk_index=i,
                total_chunks=5,
            )
            for i in range(5)
        ]

        result_chunks = []
        async for chunk in pipeline.embed_chunks(chunks):
            result_chunks.append(chunk)

        assert len(result_chunks) == 5
        # Should make 3 API calls: 2+2+1
        assert mock_openai_client.embeddings.create.call_count == 3

    @pytest.mark.asyncio
    async def test_token_counting(self, pipeline, mock_openai_client):
        """Test token counting for chunks."""
        chunks = [
            Chunk(
                chunk_id="doc-1:chunk:0",
                doc_id="doc-1",
                doc_type="test",
                text="This is a test text that should be counted for tokens.",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        result_chunks = []
        async for chunk in pipeline.embed_chunks(chunks):
            result_chunks.append(chunk)

        assert result_chunks[0].token_count is not None
        assert result_chunks[0].token_count > 0

    @pytest.mark.asyncio
    async def test_text_truncation(self, pipeline, mock_openai_client):
        """Test truncation of oversized text."""
        # Create a very long text (> max_tokens)
        long_text = "word " * 10000  # Should exceed 8191 tokens

        chunks = [
            Chunk(
                chunk_id="doc-1:chunk:0",
                doc_id="doc-1",
                doc_type="test",
                text=long_text,
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        result_chunks = []
        async for chunk in pipeline.embed_chunks(chunks):
            result_chunks.append(chunk)

        # Text should have been truncated
        assert len(result_chunks[0].text) < len(long_text)
        assert result_chunks[0].token_count is not None
        assert result_chunks[0].token_count <= pipeline.max_tokens

    @pytest.mark.asyncio
    async def test_embed_with_retry_success(self, pipeline, mock_openai_client):
        """Test successful embedding after retry."""
        # First call fails, second succeeds
        mock_openai_client.embeddings.create = AsyncMock(
            side_effect=[
                Exception("Temporary error"),
                Mock(data=[Mock(embedding=[0.1] * 1536)]),
            ]
        )

        texts = ["Test text"]
        embeddings = await pipeline._embed_with_retry(texts)

        assert len(embeddings) == 1
        assert embeddings[0] == [0.1] * 1536
        assert mock_openai_client.embeddings.create.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_with_retry_failure(self, pipeline, mock_openai_client):
        """Test embedding failure after all retries."""
        # All retries fail
        mock_openai_client.embeddings.create = AsyncMock(
            side_effect=Exception("Permanent error")
        )

        texts = ["Test text"]

        with pytest.raises(Exception, match="Permanent error"):
            await pipeline._embed_with_retry(texts)

        # Should retry max_retries times
        assert mock_openai_client.embeddings.create.call_count == 3

    @pytest.mark.asyncio
    async def test_cost_tracking(self, pipeline, mock_openai_client):
        """Test cost tracking."""
        chunks = [
            Chunk(
                chunk_id="doc-1:chunk:0",
                doc_id="doc-1",
                doc_type="test",
                text="Test chunk",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        async for _ in pipeline.embed_chunks(chunks):
            pass

        assert pipeline.total_tokens_processed > 0
        assert pipeline.total_api_calls > 0

        cost_info = pipeline.get_cost_estimate()
        assert cost_info["total_tokens"] > 0
        assert cost_info["total_api_calls"] > 0
        assert cost_info["estimated_cost_usd"] >= 0

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_openai_client):
        """Test async context manager."""
        with patch("src.indexing.embeddings.AsyncAzureOpenAI", return_value=mock_openai_client):
            async with EmbeddingPipeline(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            ) as pipeline:
                assert pipeline.client is not None

                # Use the pipeline
                embedding = await pipeline.embed_single("test")
                assert len(embedding) == 1536

            # Client should be closed after exiting context
            mock_openai_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_azure_credential(self, mock_openai_client):
        """Test initialization with DefaultAzureCredential."""
        mock_credential = AsyncMock()
        mock_credential.get_token = AsyncMock(return_value=Mock(token="test-token"))
        mock_credential.close = AsyncMock()

        with patch("src.indexing.embeddings.DefaultAzureCredential", return_value=mock_credential):
            with patch("src.indexing.embeddings.AsyncAzureOpenAI", return_value=mock_openai_client):
                pipeline = EmbeddingPipeline(
                    azure_endpoint="https://test.openai.azure.com",
                    api_key=None,  # Use DefaultAzureCredential
                )
                await pipeline._initialize_client()

                assert pipeline.client is not None
                assert pipeline._credential is not None

                await pipeline.close()
                mock_credential.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_empty_chunks(self, pipeline, mock_openai_client):
        """Test embedding empty list of chunks."""
        chunks = []

        result_chunks = []
        async for chunk in pipeline.embed_chunks(chunks):
            result_chunks.append(chunk)

        assert len(result_chunks) == 0
        mock_openai_client.embeddings.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_cost_summary(self, pipeline, mock_openai_client, caplog):
        """Test cost summary logging."""
        import logging

        caplog.set_level(logging.INFO)

        chunks = [
            Chunk(
                chunk_id="doc-1:chunk:0",
                doc_id="doc-1",
                doc_type="test",
                text="Test chunk",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        async for _ in pipeline.embed_chunks(chunks):
            pass

        pipeline.log_cost_summary()

        # Check that log contains cost information
        assert any("Embedding cost summary" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_dimensions_parameter(self, mock_openai_client):
        """Test that dimensions parameter is passed correctly."""
        with patch("src.indexing.embeddings.AsyncAzureOpenAI", return_value=mock_openai_client):
            pipeline = EmbeddingPipeline(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
                dimensions=3072,  # Use larger dimension
            )
            await pipeline._initialize_client()

            await pipeline.embed_single("test")

            # Check that dimensions was passed to API
            call_kwargs = mock_openai_client.embeddings.create.call_args.kwargs
            assert call_kwargs["dimensions"] == 3072

            await pipeline.close()
