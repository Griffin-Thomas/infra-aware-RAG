"""Application Insights integration for telemetry and monitoring.

This module provides integration with Azure Application Insights for:
- Request/response tracking
- Custom metrics
- Exception tracking
- Dependency tracking
"""

import logging
import time
from typing import Any

from fastapi import Request
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace import config_integration
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer

logger = logging.getLogger("infra_rag_api")


class ApplicationInsightsClient:
    """Client for sending telemetry to Application Insights.

    This class wraps the OpenCensus Azure exporters and provides
    convenient methods for tracking various types of telemetry.
    """

    def __init__(self, connection_string: str | None = None):
        """Initialize the Application Insights client.

        Args:
            connection_string: Application Insights connection string
                Format: InstrumentationKey=xxx;IngestionEndpoint=https://...
        """
        self.connection_string = connection_string
        self.enabled = connection_string is not None

        if self.enabled:
            # Configure OpenCensus integrations
            config_integration.trace_integrations(["requests", "httpx"])

            # Create tracer with Azure exporter
            self.tracer = Tracer(
                exporter=AzureExporter(connection_string=connection_string),
                sampler=ProbabilitySampler(1.0),  # Sample all requests
            )

            # Add Azure log handler to logger
            azure_handler = AzureLogHandler(connection_string=connection_string)
            logger.addHandler(azure_handler)
        else:
            self.tracer = None

    def track_request(
        self,
        name: str,
        url: str,
        duration_ms: int,
        response_code: int,
        success: bool,
        request_id: str | None = None,
        user_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ):
        """Track an HTTP request.

        Args:
            name: Request name (e.g., "GET /api/v1/search")
            url: Request URL
            duration_ms: Request duration in milliseconds
            response_code: HTTP response code
            success: Whether the request was successful
            request_id: Unique request identifier
            user_id: Authenticated user ID
            properties: Additional custom properties
        """
        if not self.enabled:
            return

        # Track via logging (picked up by AzureLogHandler)
        logger.info(
            f"Request: {name}",
            extra={
                "custom_dimensions": {
                    "request_name": name,
                    "url": url,
                    "duration_ms": duration_ms,
                    "response_code": response_code,
                    "success": success,
                    "request_id": request_id,
                    "user_id": user_id,
                    **(properties or {}),
                }
            },
        )

    def track_metric(
        self,
        name: str,
        value: float,
        properties: dict[str, Any] | None = None,
    ):
        """Track a custom metric.

        Args:
            name: Metric name
            value: Metric value
            properties: Additional properties/dimensions
        """
        if not self.enabled:
            return

        logger.info(
            f"Metric: {name} = {value}",
            extra={
                "custom_dimensions": {
                    "metric_name": name,
                    "metric_value": value,
                    **(properties or {}),
                }
            },
        )

    def track_exception(
        self,
        exception: Exception,
        properties: dict[str, Any] | None = None,
    ):
        """Track an exception.

        Args:
            exception: The exception to track
            properties: Additional properties
        """
        if not self.enabled:
            return

        logger.exception(
            f"Exception: {type(exception).__name__}",
            exc_info=exception,
            extra={
                "custom_dimensions": {
                    "exception_type": type(exception).__name__,
                    "exception_message": str(exception),
                    **(properties or {}),
                }
            },
        )

    def track_event(
        self,
        name: str,
        properties: dict[str, Any] | None = None,
    ):
        """Track a custom event.

        Args:
            name: Event name
            properties: Event properties
        """
        if not self.enabled:
            return

        logger.info(
            f"Event: {name}",
            extra={
                "custom_dimensions": {
                    "event_name": name,
                    **(properties or {}),
                }
            },
        )

    def flush(self):
        """Flush all pending telemetry.

        Should be called before application shutdown.
        """
        if not self.enabled:
            return

        # Force flush of all handlers
        for handler in logger.handlers:
            if hasattr(handler, "flush"):
                handler.flush()


class UsageTracker:
    """Track API usage metrics per user and endpoint.

    This class maintains usage statistics and sends them to Application Insights.
    """

    def __init__(self, app_insights: ApplicationInsightsClient):
        """Initialize the usage tracker.

        Args:
            app_insights: Application Insights client
        """
        self.app_insights = app_insights
        self._usage_stats: dict[str, dict[str, int]] = {}

    def track_request(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: int,
    ):
        """Track a request for usage statistics.

        Args:
            user_id: User identifier
            endpoint: API endpoint path
            method: HTTP method
            status_code: Response status code
            duration_ms: Request duration
        """
        # Create usage key
        key = f"{user_id}:{method}:{endpoint}"

        # Update in-memory stats
        if key not in self._usage_stats:
            self._usage_stats[key] = {
                "count": 0,
                "total_duration_ms": 0,
                "errors": 0,
            }

        self._usage_stats[key]["count"] += 1
        self._usage_stats[key]["total_duration_ms"] += duration_ms

        if status_code >= 400:
            self._usage_stats[key]["errors"] += 1

        # Send metrics to Application Insights
        self.app_insights.track_metric(
            name="api_request_count",
            value=1,
            properties={
                "user_id": user_id,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
            },
        )

        self.app_insights.track_metric(
            name="api_request_duration",
            value=duration_ms,
            properties={
                "user_id": user_id,
                "endpoint": endpoint,
                "method": method,
            },
        )

    def get_user_stats(self, user_id: str) -> dict[str, Any]:
        """Get usage statistics for a specific user.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with usage statistics
        """
        user_stats = {
            "total_requests": 0,
            "total_duration_ms": 0,
            "total_errors": 0,
            "endpoints": {},
        }

        # Aggregate stats for this user
        for key, stats in self._usage_stats.items():
            if key.startswith(f"{user_id}:"):
                user_stats["total_requests"] += stats["count"]
                user_stats["total_duration_ms"] += stats["total_duration_ms"]
                user_stats["total_errors"] += stats["errors"]

                # Extract endpoint info
                _, method, endpoint = key.split(":", 2)
                endpoint_key = f"{method} {endpoint}"
                user_stats["endpoints"][endpoint_key] = {
                    "count": stats["count"],
                    "avg_duration_ms": (
                        stats["total_duration_ms"] // stats["count"]
                        if stats["count"] > 0
                        else 0
                    ),
                    "errors": stats["errors"],
                }

        return user_stats

    def get_all_stats(self) -> dict[str, Any]:
        """Get overall usage statistics.

        Returns:
            Dictionary with aggregate statistics
        """
        total_requests = sum(stats["count"] for stats in self._usage_stats.values())
        total_errors = sum(stats["errors"] for stats in self._usage_stats.values())

        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "unique_users": len(
                set(key.split(":")[0] for key in self._usage_stats.keys())
            ),
            "endpoints": len(self._usage_stats),
        }


# Global instances (initialized in dependencies)
_app_insights: ApplicationInsightsClient | None = None
_usage_tracker: UsageTracker | None = None


def init_app_insights(connection_string: str | None):
    """Initialize Application Insights global instances.

    Args:
        connection_string: Application Insights connection string
    """
    global _app_insights, _usage_tracker

    _app_insights = ApplicationInsightsClient(connection_string)
    _usage_tracker = UsageTracker(_app_insights)


def get_app_insights() -> ApplicationInsightsClient:
    """Get the Application Insights client instance.

    Returns:
        Application Insights client

    Raises:
        RuntimeError: If not initialized
    """
    if _app_insights is None:
        raise RuntimeError("Application Insights not initialized")
    return _app_insights


def get_usage_tracker() -> UsageTracker:
    """Get the usage tracker instance.

    Returns:
        Usage tracker

    Raises:
        RuntimeError: If not initialized
    """
    if _usage_tracker is None:
        raise RuntimeError("Usage tracker not initialized")
    return _usage_tracker
