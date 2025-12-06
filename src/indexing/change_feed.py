"""Cosmos DB change feed processor for triggering indexing on new documents."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Callable

from azure.cosmos.aio import CosmosClient

from src.indexing.orchestrator import IndexingOrchestrator, IndexingStats

logger = logging.getLogger(__name__)


class ChangeFeedProcessor:
    """Processes Cosmos DB change feed to trigger indexing of new/modified documents.

    The change feed provides a real-time stream of changes to documents in a
    Cosmos DB container, enabling incremental indexing as documents are ingested.
    """

    def __init__(
        self,
        cosmos_client: CosmosClient,
        database_name: str,
        container_name: str,
        lease_container_name: str,
        indexing_orchestrator: IndexingOrchestrator,
        processor_name: str = "indexing-processor",
        max_items_per_batch: int = 100,
        poll_interval: float = 5.0,
    ):
        """Initialize change feed processor.

        Args:
            cosmos_client: Cosmos DB client
            database_name: Database name
            container_name: Source container to monitor
            lease_container_name: Container for change feed leases
            indexing_orchestrator: Orchestrator for processing documents
            processor_name: Unique name for this processor
            max_items_per_batch: Maximum documents to process in one batch
            poll_interval: Seconds to wait between polls
        """
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.lease_container_name = lease_container_name
        self.orchestrator = indexing_orchestrator
        self.processor_name = processor_name
        self.max_items_per_batch = max_items_per_batch
        self.poll_interval = poll_interval

        self.is_running = False
        self.total_processed = 0
        self.total_errors = 0

        # Callbacks for monitoring
        self.on_batch_processed: Callable[[IndexingStats], None] | None = None
        self.on_error: Callable[[Exception], None] | None = None

    async def start(self):
        """Start processing the change feed.

        This runs indefinitely until stop() is called.
        """
        if self.is_running:
            logger.warning("Change feed processor is already running")
            return

        self.is_running = True
        logger.info(f"Starting change feed processor '{self.processor_name}'")

        database = self.cosmos_client.get_database_client(self.database_name)
        container = database.get_container_client(self.container_name)
        lease_container = database.get_container_client(self.lease_container_name)

        # Initialize continuation token storage
        continuation_token = await self._load_continuation_token(lease_container)

        while self.is_running:
            try:
                # Query change feed
                response = container.query_items_change_feed(
                    is_start_from_beginning=continuation_token is None,
                    continuation=continuation_token,
                    max_item_count=self.max_items_per_batch,
                )

                # Process changes
                changes = []
                async for item in response:
                    changes.append(item)

                if changes:
                    logger.info(f"Processing {len(changes)} changes from change feed")

                    # Index the changed documents
                    stats = await self.orchestrator.index_documents(changes)

                    self.total_processed += stats.documents_processed
                    self.total_errors += len(stats.errors)

                    logger.info(
                        f"Batch complete: {stats.documents_processed} docs, "
                        f"{stats.chunks_indexed} chunks indexed, "
                        f"{len(stats.errors)} errors"
                    )

                    # Invoke callback if registered
                    if self.on_batch_processed:
                        try:
                            self.on_batch_processed(stats)
                        except Exception as e:
                            logger.error(f"Error in batch callback: {e}")

                    # Update continuation token
                    continuation_token = response.headers.get("etag")
                    await self._save_continuation_token(lease_container, continuation_token)

                else:
                    # No changes, wait before polling again
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error processing change feed: {e}", exc_info=True)
                self.total_errors += 1

                if self.on_error:
                    try:
                        self.on_error(e)
                    except Exception as callback_error:
                        logger.error(f"Error in error callback: {callback_error}")

                # Wait before retrying
                await asyncio.sleep(self.poll_interval * 2)

        logger.info("Change feed processor stopped")

    def stop(self):
        """Stop processing the change feed."""
        logger.info("Stopping change feed processor")
        self.is_running = False

    async def _load_continuation_token(self, lease_container) -> str | None:
        """Load continuation token from lease container.

        Args:
            lease_container: Container for storing leases

        Returns:
            Continuation token or None
        """
        try:
            lease_id = f"{self.processor_name}-continuation"
            item = await lease_container.read_item(item=lease_id, partition_key=lease_id)
            token = item.get("continuation_token")
            logger.info(f"Loaded continuation token: {token[:20] if token else 'None'}")
            return token
        except Exception:
            # No existing lease
            logger.info("No existing continuation token, starting from beginning")
            return None

    async def _save_continuation_token(self, lease_container, token: str | None):
        """Save continuation token to lease container.

        Args:
            lease_container: Container for storing leases
            token: Continuation token to save
        """
        try:
            lease_id = f"{self.processor_name}-continuation"
            await lease_container.upsert_item(
                {
                    "id": lease_id,
                    "continuation_token": token,
                    "processor_name": self.processor_name,
                    "last_updated": datetime.now(UTC).isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"Error saving continuation token: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get processor statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "processor_name": self.processor_name,
            "is_running": self.is_running,
            "total_processed": self.total_processed,
            "total_errors": self.total_errors,
        }


class ScheduledIndexRefresh:
    """Scheduled full index refresh for ensuring consistency.

    While the change feed provides real-time indexing, a scheduled full refresh
    ensures no documents are missed and handles any inconsistencies.
    """

    def __init__(
        self,
        indexing_orchestrator: IndexingOrchestrator,
        refresh_interval_hours: int = 24,
    ):
        """Initialize scheduled refresh.

        Args:
            indexing_orchestrator: Orchestrator for processing documents
            refresh_interval_hours: Hours between full refreshes
        """
        self.orchestrator = indexing_orchestrator
        self.refresh_interval_hours = refresh_interval_hours
        self.is_running = False
        self.last_refresh: datetime | None = None
        self.on_refresh_complete: Callable[[IndexingStats], None] | None = None

    async def start(self):
        """Start scheduled refresh loop."""
        if self.is_running:
            logger.warning("Scheduled refresh is already running")
            return

        self.is_running = True
        logger.info(f"Starting scheduled refresh (every {self.refresh_interval_hours} hours)")

        while self.is_running:
            try:
                logger.info("Starting scheduled full index refresh")

                # Run full index
                stats = await self.orchestrator.index_all_documents(incremental=False)

                self.last_refresh = datetime.now(UTC)

                logger.info(
                    f"Scheduled refresh complete: {stats.documents_processed} docs, "
                    f"{stats.chunks_indexed} chunks, "
                    f"{len(stats.errors)} errors, "
                    f"{stats.to_dict()['duration_seconds']}s"
                )

                # Invoke callback if registered
                if self.on_refresh_complete:
                    try:
                        self.on_refresh_complete(stats)
                    except Exception as e:
                        logger.error(f"Error in refresh callback: {e}")

                # Wait for next refresh
                await asyncio.sleep(self.refresh_interval_hours * 3600)

            except Exception as e:
                logger.error(f"Error during scheduled refresh: {e}", exc_info=True)
                # Wait before retrying (shorter interval on error)
                await asyncio.sleep(300)  # 5 minutes

        logger.info("Scheduled refresh stopped")

    def stop(self):
        """Stop scheduled refresh."""
        logger.info("Stopping scheduled refresh")
        self.is_running = False

    def get_stats(self) -> dict[str, Any]:
        """Get refresh statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "is_running": self.is_running,
            "refresh_interval_hours": self.refresh_interval_hours,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
        }
