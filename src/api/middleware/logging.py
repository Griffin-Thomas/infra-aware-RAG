"""Logging middleware for request/response tracking.

This middleware logs all HTTP requests and responses with relevant metadata,
integrating with Azure Application Insights for production monitoring.
"""

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Configure logger
logger = logging.getLogger("infra_rag_api")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log HTTP requests and responses.

    This middleware:
    1. Assigns a unique request ID to each request
    2. Logs request details (method, path, client, user)
    3. Measures request duration
    4. Logs response details (status code, duration)
    5. Integrates with Application Insights
    """

    def __init__(
        self,
        app,
        enabled: bool = True,
        log_request_body: bool = False,
        log_response_body: bool = False,
    ):
        """Initialize the logging middleware.

        Args:
            app: The FastAPI application
            enabled: Whether logging is enabled (default: True)
            log_request_body: Whether to log request bodies (default: False, can expose secrets)
            log_response_body: Whether to log response bodies (default: False, can be verbose)
        """
        super().__init__(app)
        self.enabled = enabled
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body

    async def dispatch(self, request: Request, call_next: Callable):
        """Process the request and log details.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            The response from the next handler
        """
        if not self.enabled:
            return await call_next(request)

        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Get client info
        client_id = self._get_client_id(request)
        client_ip = self._get_client_ip(request)

        # Get user info if authenticated
        user_id = None
        if hasattr(request.state, "user") and request.state.user:
            user_id = request.state.user.get("sub") or request.state.user.get("email")

        # Start timer
        start_time = time.time()

        # Log request
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_id": client_id,
                "client_ip": client_ip,
                "user_id": user_id,
                "user_agent": request.headers.get("user-agent"),
            },
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error
            duration = time.time() - start_time
            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": int(duration * 1000),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

        # Calculate duration
        duration = time.time() - start_time

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response
        log_level = logging.INFO
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING

        logger.log(
            log_level,
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": int(duration * 1000),
                "client_id": client_id,
                "client_ip": client_ip,
                "user_id": user_id,
            },
        )

        # Track metrics
        self._track_metrics(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=duration,
            request_id=request_id,
            user_id=user_id,
        )

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier.

        Args:
            request: The FastAPI request

        Returns:
            Client identifier string
        """
        if hasattr(request.state, "user") and request.state.user:
            return request.state.user.get("sub", "unknown")
        return self._get_client_ip(request)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address.

        Args:
            request: The FastAPI request

        Returns:
            Client IP address
        """
        # Check for X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check for X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to client.host
        return request.client.host if request.client else "unknown"

    def _track_metrics(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        request_id: str | None = None,
        user_id: str | None = None,
    ):
        """Track metrics for monitoring.

        Sends metrics to Azure Application Insights if configured.

        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            duration: Request duration in seconds
            request_id: Request ID
            user_id: User ID (if authenticated)
        """
        try:
            from .app_insights import get_app_insights, get_usage_tracker

            # Track request in Application Insights
            app_insights = get_app_insights()
            app_insights.track_request(
                name=f"{method} {path}",
                url=path,
                duration_ms=int(duration * 1000),
                response_code=status_code,
                success=status_code < 400,
                request_id=request_id,
                user_id=user_id,
            )

            # Track usage statistics
            if user_id:
                usage_tracker = get_usage_tracker()
                usage_tracker.track_request(
                    user_id=user_id,
                    endpoint=path,
                    method=method,
                    status_code=status_code,
                    duration_ms=int(duration * 1000),
                )
        except (ImportError, RuntimeError):
            # Application Insights not configured - skip tracking
            pass


def configure_logging(
    log_level: str = "INFO",
    app_insights_key: str | None = None,
):
    """Configure application logging.

    Sets up structured logging with optional Application Insights integration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        app_insights_key: Azure Application Insights instrumentation key
    """
    # Configure basic logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Configure Application Insights if key provided
    if app_insights_key:
        try:
            from applicationinsights.logging import LoggingHandler

            # Add Application Insights handler
            handler = LoggingHandler(app_insights_key)
            logger.addHandler(handler)
            logger.info("Application Insights logging configured")
        except ImportError:
            logger.warning(
                "Application Insights package not installed. "
                "Install with: pip install applicationinsights"
            )


class StructuredLogger:
    """Structured logger for consistent log formatting.

    This class provides convenience methods for logging with structured data.
    """

    def __init__(self, name: str):
        """Initialize the structured logger.

        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)

    def info(self, message: str, **kwargs):
        """Log info message with structured data.

        Args:
            message: Log message
            **kwargs: Additional structured data
        """
        self.logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message with structured data.

        Args:
            message: Log message
            **kwargs: Additional structured data
        """
        self.logger.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs):
        """Log error message with structured data.

        Args:
            message: Log message
            **kwargs: Additional structured data
        """
        self.logger.error(message, extra=kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug message with structured data.

        Args:
            message: Log message
            **kwargs: Additional structured data
        """
        self.logger.debug(message, extra=kwargs)
