"""Monitoring and alerting for indexing pipeline."""

import logging
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from src.indexing.orchestrator import IndexingStats

logger = logging.getLogger(__name__)


class IndexingMonitor:
    """Monitors indexing pipeline health and tracks metrics.

    Provides real-time monitoring of indexing operations, tracks failure rates,
    and can trigger alerts when issues are detected.
    """

    def __init__(
        self,
        error_threshold: float = 0.1,  # 10% error rate triggers alert
        history_size: int = 100,  # Keep last 100 batches
        alert_cooldown_minutes: int = 30,  # Don't spam alerts
    ):
        """Initialize monitoring.

        Args:
            error_threshold: Error rate threshold (0.0-1.0) for triggering alerts
            history_size: Number of recent batches to keep in history
            alert_cooldown_minutes: Minimum minutes between alerts
        """
        self.error_threshold = error_threshold
        self.history_size = history_size
        self.alert_cooldown = timedelta(minutes=alert_cooldown_minutes)

        # Metrics tracking
        self.total_documents_processed = 0
        self.total_chunks_indexed = 0
        self.total_errors = 0
        self.batch_history: deque[IndexingStats] = deque(maxlen=history_size)

        # Alert tracking
        self.last_alert_time: datetime | None = None
        self.alert_handlers: list = []

        # Start time
        self.start_time = datetime.now(UTC)

    def record_batch(self, stats: IndexingStats):
        """Record statistics from a batch indexing operation.

        Args:
            stats: Indexing statistics to record
        """
        self.batch_history.append(stats)
        self.total_documents_processed += stats.documents_processed
        self.total_chunks_indexed += stats.chunks_indexed
        self.total_errors += len(stats.errors)

        # Check for alerts
        self._check_error_rate(stats)

        logger.info(
            f"Batch recorded: {stats.documents_processed} docs, "
            f"{stats.chunks_indexed} chunks, "
            f"{len(stats.errors)} errors"
        )

    def _check_error_rate(self, stats: IndexingStats):
        """Check if error rate exceeds threshold and trigger alert.

        Args:
            stats: Latest batch statistics
        """
        if stats.documents_processed == 0:
            return

        error_rate = len(stats.errors) / stats.documents_processed

        if error_rate >= self.error_threshold:
            # Check cooldown
            if self.last_alert_time and (datetime.now(UTC) - self.last_alert_time) < self.alert_cooldown:
                logger.debug("Alert suppressed due to cooldown")
                return

            # Trigger alert
            alert_data = {
                "type": "high_error_rate",
                "error_rate": error_rate,
                "threshold": self.error_threshold,
                "documents_processed": stats.documents_processed,
                "errors": stats.errors,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            logger.error(
                f"HIGH ERROR RATE ALERT: {error_rate:.1%} error rate "
                f"({len(stats.errors)}/{stats.documents_processed} docs failed)"
            )

            self._trigger_alert(alert_data)
            self.last_alert_time = datetime.now(UTC)

    def _trigger_alert(self, alert_data: dict[str, Any]):
        """Trigger all registered alert handlers.

        Args:
            alert_data: Alert information
        """
        for handler in self.alert_handlers:
            try:
                handler(alert_data)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")

    def register_alert_handler(self, handler):
        """Register a callback for alerts.

        Args:
            handler: Callable that receives alert_data dict
        """
        self.alert_handlers.append(handler)
        logger.info(f"Registered alert handler: {handler}")

    def get_metrics(self) -> dict[str, Any]:
        """Get current monitoring metrics.

        Returns:
            Dictionary with metrics
        """
        uptime = (datetime.now(UTC) - self.start_time).total_seconds()

        # Calculate recent error rate
        recent_error_rate = 0.0
        if self.batch_history:
            recent_errors = sum(len(batch.errors) for batch in self.batch_history)
            recent_docs = sum(batch.documents_processed for batch in self.batch_history)
            if recent_docs > 0:
                recent_error_rate = recent_errors / recent_docs

        # Calculate overall error rate
        overall_error_rate = 0.0
        if self.total_documents_processed > 0:
            overall_error_rate = self.total_errors / self.total_documents_processed

        # Calculate throughput
        docs_per_second = self.total_documents_processed / uptime if uptime > 0 else 0
        chunks_per_second = self.total_chunks_indexed / uptime if uptime > 0 else 0

        return {
            "uptime_seconds": round(uptime, 2),
            "total_documents_processed": self.total_documents_processed,
            "total_chunks_indexed": self.total_chunks_indexed,
            "total_errors": self.total_errors,
            "overall_error_rate": round(overall_error_rate, 4),
            "recent_error_rate": round(recent_error_rate, 4),
            "error_threshold": self.error_threshold,
            "docs_per_second": round(docs_per_second, 2),
            "chunks_per_second": round(chunks_per_second, 2),
            "batches_processed": len(self.batch_history),
            "last_alert_time": self.last_alert_time.isoformat() if self.last_alert_time else None,
        }

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent errors from batch history.

        Args:
            limit: Maximum number of errors to return

        Returns:
            List of recent errors
        """
        errors = []

        # Collect errors from recent batches (newest first)
        for batch in reversed(self.batch_history):
            for error in batch.errors:
                errors.append(error)
                if len(errors) >= limit:
                    return errors

        return errors

    def get_health_status(self) -> dict[str, Any]:
        """Get overall health status.

        Returns:
            Health status dictionary with status and details
        """
        metrics = self.get_metrics()

        # Determine health status
        status = "healthy"
        issues = []

        if metrics["recent_error_rate"] >= self.error_threshold:
            status = "degraded"
            issues.append(f"High error rate: {metrics['recent_error_rate']:.1%}")

        if metrics["total_errors"] > 0 and metrics["total_documents_processed"] == 0:
            status = "unhealthy"
            issues.append("No documents successfully processed")

        return {
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": metrics,
            "issues": issues,
        }

    def reset(self):
        """Reset all metrics (for testing or fresh start)."""
        self.total_documents_processed = 0
        self.total_chunks_indexed = 0
        self.total_errors = 0
        self.batch_history.clear()
        self.last_alert_time = None
        self.start_time = datetime.now(UTC)
        logger.info("Monitor metrics reset")


class AlertHandlers:
    """Pre-built alert handlers for common scenarios."""

    @staticmethod
    def log_alert(alert_data: dict[str, Any]):
        """Log alert to standard logging.

        Args:
            alert_data: Alert information
        """
        logger.error(f"INDEXING ALERT: {alert_data}")

    @staticmethod
    def console_alert(alert_data: dict[str, Any]):
        """Print alert to console.

        Args:
            alert_data: Alert information
        """
        print(f"\n⚠️  INDEXING ALERT: {alert_data['type']}")
        print(f"   Error Rate: {alert_data['error_rate']:.1%}")
        print(f"   Threshold: {alert_data['threshold']:.1%}")
        print(f"   Documents Processed: {alert_data['documents_processed']}")
        print(f"   Errors: {len(alert_data['errors'])}")
        print(f"   Time: {alert_data['timestamp']}\n")

    @staticmethod
    def create_webhook_alert(webhook_url: str):
        """Create webhook alert handler.

        Args:
            webhook_url: URL to POST alerts to

        Returns:
            Alert handler function
        """
        import httpx

        async def webhook_alert(alert_data: dict[str, Any]):
            """Send alert to webhook."""
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        webhook_url,
                        json=alert_data,
                        timeout=10.0,
                    )
                    response.raise_for_status()
                    logger.info(f"Alert sent to webhook: {webhook_url}")
            except Exception as e:
                logger.error(f"Error sending alert to webhook: {e}")

        return webhook_alert
