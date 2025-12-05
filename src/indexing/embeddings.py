"""Embedding pipeline for generating vector embeddings from chunks."""

import asyncio
import logging
from typing import AsyncIterator

import tiktoken
from azure.identity.aio import DefaultAzureCredential
from openai import AsyncAzureOpenAI

from src.indexing.models import Chunk

logger = logging.getLogger(__name__)


class EmbeddingPipeline:
    """Pipeline for generating embeddings from chunks using Azure OpenAI."""

    def __init__(
        self,
        azure_endpoint: str,
        api_key: str | None = None,  # Uses DefaultAzureCredential if None
        model: str = "text-embedding-3-large",
        dimensions: int = 1536,
        batch_size: int = 16,
        max_retries: int = 3,
        max_tokens: int = 8191,  # Max tokens for text-embedding-3-large
    ):
        """Initialize embedding pipeline.

        Args:
            azure_endpoint: Azure OpenAI endpoint URL
            api_key: API key (if None, uses DefaultAzureCredential)
            model: Embedding model name
            dimensions: Embedding dimensions (256, 1024, 1536, or 3072 for text-embedding-3-large)
            batch_size: Number of texts to embed per API call
            max_retries: Maximum number of retry attempts
            max_tokens: Maximum tokens per text (truncates if exceeded)
        """
        self.azure_endpoint = azure_endpoint
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.max_tokens = max_tokens

        # Initialize client (will be set up in async context)
        self.client: AsyncAzureOpenAI | None = None
        self._api_key = api_key
        self._credential: DefaultAzureCredential | None = None

        # Token counter
        self.encoding = tiktoken.get_encoding("cl100k_base")

        # Cost tracking
        self.total_tokens_processed = 0
        self.total_api_calls = 0

    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _initialize_client(self):
        """Initialize the Azure OpenAI client."""
        if self.client is not None:
            return

        if self._api_key:
            self.client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                api_key=self._api_key,
                api_version="2024-02-01",
            )
        else:
            self._credential = DefaultAzureCredential()
            # Note: azure_ad_token_provider requires a callable that returns a token
            # For simplicity, we'll use the credential directly with get_token
            self.client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                azure_ad_token_provider=self._get_token_provider(),
                api_version="2024-02-01",
            )

    def _get_token_provider(self):
        """Get token provider function for Azure AD authentication."""
        async def get_token():
            if self._credential is None:
                raise RuntimeError("Credential not initialized")
            token = await self._credential.get_token("https://cognitiveservices.azure.com/.default")
            return token.token
        return get_token

    async def close(self):
        """Close the client and cleanup resources."""
        if self.client:
            await self.client.close()
            self.client = None
        if self._credential:
            await self._credential.close()
            self._credential = None

    async def embed_chunks(
        self,
        chunks: list[Chunk],
    ) -> AsyncIterator[Chunk]:
        """Generate embeddings for chunks.

        Args:
            chunks: List of chunks to embed

        Yields:
            Chunks with embeddings populated

        Raises:
            RuntimeError: If client is not initialized
        """
        if self.client is None:
            await self._initialize_client()

        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]

            # Prepare texts and handle truncation
            texts = []
            for chunk in batch:
                # Count tokens and truncate if needed
                tokens = self.encoding.encode(chunk.text)
                if len(tokens) > self.max_tokens:
                    logger.warning(
                        f"Chunk {chunk.chunk_id} has {len(tokens)} tokens, truncating to {self.max_tokens}"
                    )
                    # Truncate with some buffer to ensure we're under limit
                    truncated_tokens = tokens[: self.max_tokens - 100]
                    chunk.text = self.encoding.decode(truncated_tokens)
                    tokens = truncated_tokens

                chunk.token_count = len(tokens)
                texts.append(chunk.text)

            # Generate embeddings
            embeddings = await self._embed_with_retry(texts)

            # Track costs
            self.total_tokens_processed += sum(chunk.token_count or 0 for chunk in batch)
            self.total_api_calls += 1

            # Yield chunks with embeddings
            for chunk, embedding in zip(batch, embeddings):
                chunk.embedding = embedding
                chunk.embedding_model = self.model
                yield chunk

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings with retry logic.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings (vectors)

        Raises:
            Exception: If all retries fail
        """
        if self.client is None:
            raise RuntimeError("Client not initialized")

        for attempt in range(self.max_retries):
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                    dimensions=self.dimensions,
                )
                return [item.embedding for item in response.data]

            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Embedding failed after {self.max_retries} attempts: {e}")
                    raise

                wait_time = 2**attempt
                logger.warning(f"Embedding failed (attempt {attempt + 1}/{self.max_retries}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

        # Should never reach here, but for type safety
        raise RuntimeError("Failed to generate embeddings after all retries")

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            RuntimeError: If client is not initialized
        """
        if self.client is None:
            await self._initialize_client()

        # Count and truncate if needed
        tokens = self.encoding.encode(text)
        if len(tokens) > self.max_tokens:
            logger.warning(f"Text has {len(tokens)} tokens, truncating to {self.max_tokens}")
            truncated_tokens = tokens[: self.max_tokens - 100]
            text = self.encoding.decode(truncated_tokens)

        response = await self.client.embeddings.create(
            model=self.model,
            input=[text],
            dimensions=self.dimensions,
        )

        # Track costs
        self.total_tokens_processed += len(tokens)
        self.total_api_calls += 1

        return response.data[0].embedding

    def get_cost_estimate(self) -> dict[str, float]:
        """Get estimated cost based on tokens processed.

        Returns:
            Dictionary with cost breakdown

        Note:
            Pricing for text-embedding-3-large (as of 2024):
            - $0.13 per 1M tokens
        """
        cost_per_million_tokens = 0.13
        estimated_cost = (self.total_tokens_processed / 1_000_000) * cost_per_million_tokens

        return {
            "total_tokens": self.total_tokens_processed,
            "total_api_calls": self.total_api_calls,
            "estimated_cost_usd": round(estimated_cost, 4),
            "cost_per_million_tokens": cost_per_million_tokens,
        }

    def log_cost_summary(self):
        """Log cost summary."""
        cost_info = self.get_cost_estimate()
        logger.info(
            f"Embedding cost summary: "
            f"{cost_info['total_tokens']:,} tokens processed, "
            f"{cost_info['total_api_calls']} API calls, "
            f"estimated cost: ${cost_info['estimated_cost_usd']:.4f} USD"
        )
