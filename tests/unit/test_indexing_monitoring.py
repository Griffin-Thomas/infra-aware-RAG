"""Unit tests for indexing monitoring."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from src.indexing.monitoring import AlertHandlers, IndexingMonitor
from src.indexing.orchestrator import IndexingStats


@pytest.fixture
def monitor():
    """Create test monitor."""
    return IndexingMonitor(error_threshold=0.1, history_size=10, alert_cooldown_minutes=1)


class TestIndexingMonitor:
    """Test suite for IndexingMonitor."""

    def test_init(self, monitor):
        """Test monitor initialization."""
        assert monitor.error_threshold == 0.1
        assert monitor.history_size == 10
        assert monitor.total_documents_processed == 0
        assert monitor.total_chunks_indexed == 0
        assert monitor.total_errors == 0
        assert len(monitor.batch_history) == 0
        assert monitor.last_alert_time is None

    def test_record_batch(self, monitor):
        """Test recording batch statistics."""
        stats = IndexingStats()
        stats.documents_processed = 10
        stats.chunks_indexed = 50
        stats.chunks_embedded = 50
        stats.chunks_created = 50

        monitor.record_batch(stats)

        assert monitor.total_documents_processed == 10
        assert monitor.total_chunks_indexed == 50
        assert len(monitor.batch_history) == 1

    def test_record_multiple_batches(self, monitor):
        """Test recording multiple batches."""
        for i in range(5):
            stats = IndexingStats()
            stats.documents_processed = 10
            stats.chunks_indexed = 50
            monitor.record_batch(stats)

        assert monitor.total_documents_processed == 50
        assert monitor.total_chunks_indexed == 250
        assert len(monitor.batch_history) == 5

    def test_batch_history_limit(self):
        """Test that batch history respects size limit."""
        monitor = IndexingMonitor(history_size=3)

        # Record more batches than history size
        for i in range(5):
            stats = IndexingStats()
            stats.documents_processed = 1
            monitor.record_batch(stats)

        # Should only keep last 3
        assert len(monitor.batch_history) == 3

    def test_error_rate_no_alert(self, monitor):
        """Test that low error rate doesn't trigger alert."""
        stats = IndexingStats()
        stats.documents_processed = 100
        stats.record_error("doc-1", "Error 1")  # 1% error rate

        handler = Mock()
        monitor.register_alert_handler(handler)

        monitor.record_batch(stats)

        # Should not trigger alert (below 10% threshold)
        handler.assert_not_called()

    def test_error_rate_triggers_alert(self, monitor):
        """Test that high error rate triggers alert."""
        stats = IndexingStats()
        stats.documents_processed = 10

        # Add errors to exceed threshold
        for i in range(2):  # 20% error rate
            stats.record_error(f"doc-{i}", f"Error {i}")

        handler = Mock()
        monitor.register_alert_handler(handler)

        monitor.record_batch(stats)

        # Should trigger alert
        handler.assert_called_once()

        # Check alert data
        alert_data = handler.call_args[0][0]
        assert alert_data["type"] == "high_error_rate"
        assert alert_data["error_rate"] == 0.2
        assert alert_data["threshold"] == 0.1

    def test_alert_cooldown(self, monitor):
        """Test that alert cooldown prevents spam."""
        handler = Mock()
        monitor.register_alert_handler(handler)

        # First alert
        stats1 = IndexingStats()
        stats1.documents_processed = 10
        for i in range(2):
            stats1.record_error(f"doc-{i}", "Error")
        monitor.record_batch(stats1)

        assert handler.call_count == 1

        # Second alert immediately after (should be suppressed)
        stats2 = IndexingStats()
        stats2.documents_processed = 10
        for i in range(2):
            stats2.record_error(f"doc-{i}", "Error")
        monitor.record_batch(stats2)

        # Still only 1 call due to cooldown
        assert handler.call_count == 1

    def test_get_metrics(self, monitor):
        """Test getting monitoring metrics."""
        # Record some batches
        for i in range(3):
            stats = IndexingStats()
            stats.documents_processed = 10
            stats.chunks_indexed = 50
            monitor.record_batch(stats)

        metrics = monitor.get_metrics()

        assert metrics["total_documents_processed"] == 30
        assert metrics["total_chunks_indexed"] == 150
        assert metrics["total_errors"] == 0
        assert metrics["overall_error_rate"] == 0.0
        assert metrics["batches_processed"] == 3
        assert metrics["uptime_seconds"] >= 0  # Allow for very fast execution

    def test_get_metrics_with_errors(self, monitor):
        """Test metrics with errors."""
        stats = IndexingStats()
        stats.documents_processed = 100
        for i in range(5):
            stats.record_error(f"doc-{i}", "Error")

        monitor.record_batch(stats)

        metrics = monitor.get_metrics()

        assert metrics["total_errors"] == 5
        assert metrics["overall_error_rate"] == 0.05

    def test_get_metrics_throughput(self, monitor):
        """Test throughput calculations."""
        stats = IndexingStats()
        stats.documents_processed = 100
        stats.chunks_indexed = 500
        monitor.record_batch(stats)

        metrics = monitor.get_metrics()

        assert metrics["docs_per_second"] > 0
        assert metrics["chunks_per_second"] > 0

    def test_get_recent_errors(self, monitor):
        """Test getting recent errors."""
        # Record batches with errors
        for i in range(3):
            stats = IndexingStats()
            stats.documents_processed = 10
            stats.record_error(f"doc-{i}", f"Error {i}")
            monitor.record_batch(stats)

        errors = monitor.get_recent_errors(limit=10)

        assert len(errors) == 3
        assert errors[0]["doc_id"] == "doc-2"  # Most recent first

    def test_get_recent_errors_limit(self, monitor):
        """Test recent errors respects limit."""
        # Record many errors
        for i in range(10):
            stats = IndexingStats()
            stats.documents_processed = 1
            stats.record_error(f"doc-{i}", "Error")
            monitor.record_batch(stats)

        errors = monitor.get_recent_errors(limit=5)

        assert len(errors) == 5

    def test_get_health_status_healthy(self, monitor):
        """Test health status when system is healthy."""
        stats = IndexingStats()
        stats.documents_processed = 100
        stats.chunks_indexed = 500
        monitor.record_batch(stats)

        health = monitor.get_health_status()

        assert health["status"] == "healthy"
        assert len(health["issues"]) == 0

    def test_get_health_status_degraded(self, monitor):
        """Test health status when error rate is high."""
        stats = IndexingStats()
        stats.documents_processed = 10
        for i in range(2):  # 20% error rate
            stats.record_error(f"doc-{i}", "Error")
        monitor.record_batch(stats)

        health = monitor.get_health_status()

        assert health["status"] == "degraded"
        assert len(health["issues"]) > 0
        assert "High error rate" in health["issues"][0]

    def test_get_health_status_unhealthy(self, monitor):
        """Test health status when no documents processed."""
        stats = IndexingStats()
        stats.documents_processed = 0
        stats.record_error("doc-1", "Error")
        monitor.record_batch(stats)

        health = monitor.get_health_status()

        assert health["status"] == "unhealthy"
        assert any("No documents successfully processed" in issue for issue in health["issues"])

    def test_reset(self, monitor):
        """Test resetting metrics."""
        # Record some data
        stats = IndexingStats()
        stats.documents_processed = 100
        stats.chunks_indexed = 500
        monitor.record_batch(stats)

        assert monitor.total_documents_processed > 0

        # Reset
        monitor.reset()

        assert monitor.total_documents_processed == 0
        assert monitor.total_chunks_indexed == 0
        assert monitor.total_errors == 0
        assert len(monitor.batch_history) == 0

    def test_multiple_alert_handlers(self, monitor):
        """Test multiple alert handlers are called."""
        handler1 = Mock()
        handler2 = Mock()

        monitor.register_alert_handler(handler1)
        monitor.register_alert_handler(handler2)

        # Trigger alert
        stats = IndexingStats()
        stats.documents_processed = 10
        for i in range(2):
            stats.record_error(f"doc-{i}", "Error")
        monitor.record_batch(stats)

        handler1.assert_called_once()
        handler2.assert_called_once()

    def test_alert_handler_error_doesnt_break_monitoring(self, monitor):
        """Test that alert handler errors don't break monitoring."""

        def bad_handler(alert_data):
            raise Exception("Handler error")

        monitor.register_alert_handler(bad_handler)

        # Trigger alert - should not raise
        stats = IndexingStats()
        stats.documents_processed = 10
        for i in range(2):
            stats.record_error(f"doc-{i}", "Error")

        monitor.record_batch(stats)  # Should not raise


class TestAlertHandlers:
    """Test suite for AlertHandlers."""

    def test_log_alert(self, caplog):
        """Test log alert handler."""
        alert_data = {
            "type": "high_error_rate",
            "error_rate": 0.2,
            "threshold": 0.1,
        }

        AlertHandlers.log_alert(alert_data)

        assert "INDEXING ALERT" in caplog.text

    def test_console_alert(self, capsys):
        """Test console alert handler."""
        alert_data = {
            "type": "high_error_rate",
            "error_rate": 0.2,
            "threshold": 0.1,
            "documents_processed": 10,
            "errors": [{"doc_id": "doc-1", "error": "Error"}],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        AlertHandlers.console_alert(alert_data)

        captured = capsys.readouterr()
        assert "INDEXING ALERT" in captured.out
        assert "Error Rate: 20.0%" in captured.out

    def test_create_webhook_alert(self):
        """Test creating webhook alert handler."""
        handler = AlertHandlers.create_webhook_alert("https://example.com/webhook")

        assert callable(handler)
