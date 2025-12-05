"""Azure AI Search indexer for batch document uploads."""

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

from src.indexing.models import Chunk

logger = logging.getLogger(__name__)


class SearchIndexer:
    """Populates the Azure AI Search index with chunks."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        index_name: str = "infra-index",
        batch_size: int = 100,
    ):
        """Initialize search indexer.

        Args:
            endpoint: Azure AI Search endpoint URL
            api_key: API key (if None, uses DefaultAzureCredential)
            index_name: Name of the index to populate
            batch_size: Number of documents per batch upload
        """
        self.endpoint = endpoint
        self.index_name = index_name
        self.batch_size = batch_size

        # Initialize client
        if api_key:
            self.search_client = SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(api_key),
            )
        else:
            credential = DefaultAzureCredential()
            self.search_client = SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=credential,
            )

    def index_chunks(self, chunks: Iterator[Chunk]) -> dict[str, Any]:
        """Index chunks in batches.

        Args:
            chunks: Iterator of chunks to index

        Returns:
            Dictionary with statistics about the indexing operation:
            - total: Total documents processed
            - succeeded: Number of successful uploads
            - failed: Number of failed uploads
            - errors: List of error details
        """
        stats = {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

        batch = []
        for chunk in chunks:
            batch.append(chunk.to_search_document())

            if len(batch) >= self.batch_size:
                self._upload_batch(batch, stats)
                batch = []

        # Upload remaining documents
        if batch:
            self._upload_batch(batch, stats)

        logger.info(
            f"Indexing complete: {stats['succeeded']}/{stats['total']} succeeded, "
            f"{stats['failed']} failed"
        )

        return stats

    async def index_chunks_async(
        self, chunks: AsyncIterator[Chunk]
    ) -> dict[str, Any]:
        """Index chunks in batches asynchronously.

        Args:
            chunks: Async iterator of chunks to index

        Returns:
            Dictionary with indexing statistics
        """
        stats = {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

        batch = []
        async for chunk in chunks:
            batch.append(chunk.to_search_document())

            if len(batch) >= self.batch_size:
                self._upload_batch(batch, stats)
                batch = []

        # Upload remaining documents
        if batch:
            self._upload_batch(batch, stats)

        logger.info(
            f"Async indexing complete: {stats['succeeded']}/{stats['total']} succeeded, "
            f"{stats['failed']} failed"
        )

        return stats

    def _upload_batch(self, batch: list[dict], stats: dict[str, Any]):
        """Upload a batch of documents to the index.

        Args:
            batch: List of document dictionaries
            stats: Statistics dictionary to update

        Note:
            Updates stats in-place
        """
        if not batch:
            return

        try:
            results = self.search_client.upload_documents(documents=batch)

            # Process results
            for result in results:
                stats["total"] += 1
                if result.succeeded:
                    stats["succeeded"] += 1
                else:
                    stats["failed"] += 1
                    error_info = {
                        "key": result.key,
                        "error": result.error_message if hasattr(result, "error_message") else "Unknown error",
                        "status_code": result.status_code if hasattr(result, "status_code") else None,
                    }
                    stats["errors"].append(error_info)
                    logger.warning(f"Failed to index document {result.key}: {error_info['error']}")

        except HttpResponseError as e:
            # Batch-level error
            stats["total"] += len(batch)
            stats["failed"] += len(batch)
            error_info = {
                "error": str(e),
                "status_code": e.status_code if hasattr(e, "status_code") else None,
                "batch_size": len(batch),
            }
            stats["errors"].append(error_info)
            logger.error(f"Failed to upload batch of {len(batch)} documents: {e}")

        except Exception as e:
            # Unexpected error
            stats["total"] += len(batch)
            stats["failed"] += len(batch)
            error_info = {
                "error": str(e),
                "error_type": type(e).__name__,
                "batch_size": len(batch),
            }
            stats["errors"].append(error_info)
            logger.error(f"Unexpected error uploading batch: {e}")

    def delete_documents(self, ids: list[str]) -> dict[str, Any]:
        """Delete documents by ID.

        Args:
            ids: List of document IDs to delete

        Returns:
            Dictionary with deletion statistics
        """
        if not ids:
            return {"total": 0, "succeeded": 0, "failed": 0, "errors": []}

        stats = {
            "total": len(ids),
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

        try:
            # Prepare documents for deletion
            documents = [{"id": doc_id} for doc_id in ids]

            # Delete in batches
            for i in range(0, len(documents), self.batch_size):
                batch = documents[i : i + self.batch_size]
                results = self.search_client.delete_documents(documents=batch)

                # Process results
                for result in results:
                    if result.succeeded:
                        stats["succeeded"] += 1
                    else:
                        stats["failed"] += 1
                        error_info = {
                            "key": result.key,
                            "error": result.error_message if hasattr(result, "error_message") else "Unknown error",
                        }
                        stats["errors"].append(error_info)

            logger.info(
                f"Deletion complete: {stats['succeeded']}/{stats['total']} succeeded, "
                f"{stats['failed']} failed"
            )

        except Exception as e:
            stats["failed"] = stats["total"]
            stats["succeeded"] = 0
            stats["errors"].append({"error": str(e)})
            logger.error(f"Failed to delete documents: {e}")

        return stats

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Retrieve a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dictionary or None if not found
        """
        try:
            result = self.search_client.get_document(key=doc_id)
            return result
        except HttpResponseError as e:
            if e.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            raise

    def close(self):
        """Close the client and cleanup resources."""
        if self.search_client:
            self.search_client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
