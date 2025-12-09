"""Rate limiting middleware for API protection.

This middleware implements token bucket rate limiting with both per-minute
and per-hour limits. It tracks requests by user ID (if authenticated) or IP address.
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class TokenBucket:
    """Token bucket for rate limiting.

    Implements the token bucket algorithm for smooth rate limiting.
    """

    def __init__(self, capacity: int, refill_rate: float):
        """Initialize the token bucket.

        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        # Refill tokens based on time passed
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate),
        )
        self.last_refill = now

        # Try to consume
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using token bucket algorithm.

    Enforces both per-minute and per-hour rate limits to protect the API
    from abuse while allowing legitimate bursts of traffic.
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        enabled: bool = True,
    ):
        """Initialize the rate limiting middleware.

        Args:
            app: The FastAPI application
            requests_per_minute: Maximum requests per minute per client
            requests_per_hour: Maximum requests per hour per client
            enabled: Whether rate limiting is enabled (default: True)
        """
        super().__init__(app)
        self.enabled = enabled
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

        # Token buckets per client: {client_id: {"minute": bucket, "hour": bucket}}
        self._buckets: dict[str, dict[str, TokenBucket]] = defaultdict(
            lambda: {
                "minute": TokenBucket(
                    capacity=requests_per_minute,
                    refill_rate=requests_per_minute / 60.0,  # tokens per second
                ),
                "hour": TokenBucket(
                    capacity=requests_per_hour,
                    refill_rate=requests_per_hour / 3600.0,  # tokens per second
                ),
            }
        )

        # Lock for thread-safe access
        self._lock = asyncio.Lock()

        # Cleanup old buckets periodically
        self._last_cleanup = time.time()
        self._cleanup_interval = 3600  # 1 hour

    async def dispatch(self, request: Request, call_next):
        """Process the request and enforce rate limits.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            The response from the next handler

        Raises:
            HTTPException: If rate limit is exceeded
        """
        # Skip rate limiting if disabled
        if not self.enabled:
            return await call_next(request)

        # Get client identifier
        client_id = self._get_client_id(request)

        # Check rate limits
        async with self._lock:
            # Periodic cleanup
            await self._cleanup_old_buckets()

            # Get or create buckets for this client
            buckets = self._buckets[client_id]

            # Check per-minute limit
            if not buckets["minute"].consume():
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded (per minute)",
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time() + 60)),
                    },
                )

            # Check per-hour limit
            if not buckets["hour"].consume():
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded (per hour)",
                    headers={
                        "Retry-After": "3600",
                        "X-RateLimit-Limit": str(self.requests_per_hour),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time() + 3600)),
                    },
                )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting.

        Prefers user ID from authentication, falls back to IP address.

        Args:
            request: The FastAPI request

        Returns:
            Client identifier string
        """
        # Prefer user ID from auth
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.get('sub', 'unknown')}"

        # Fall back to IP address
        # Check for X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return f"ip:{client_ip}"

    async def _cleanup_old_buckets(self):
        """Remove old token buckets to prevent memory growth.

        This is called periodically during request processing.
        """
        now = time.time()

        # Only cleanup once per interval
        if now - self._last_cleanup < self._cleanup_interval:
            return

        # Remove buckets that are full (no activity)
        # This is a simple heuristic - full buckets likely haven't been used recently
        to_remove = []
        for client_id, buckets in self._buckets.items():
            if (
                buckets["minute"].tokens >= buckets["minute"].capacity * 0.99
                and buckets["hour"].tokens >= buckets["hour"].capacity * 0.99
            ):
                to_remove.append(client_id)

        for client_id in to_remove:
            del self._buckets[client_id]

        self._last_cleanup = now


class SlidingWindowRateLimiter:
    """Alternative rate limiter using sliding window algorithm.

    This is more precise than token bucket but uses more memory.
    Not currently used, but provided as an alternative implementation.
    """

    def __init__(self, window_size: int, max_requests: int):
        """Initialize the sliding window rate limiter.

        Args:
            window_size: Window size in seconds
            max_requests: Maximum requests in the window
        """
        self.window_size = window_size
        self.max_requests = max_requests
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if a request is allowed.

        Args:
            client_id: Client identifier

        Returns:
            True if request is allowed, False otherwise
        """
        now = time.time()
        window_start = now - self.window_size

        # Clean old requests
        self._requests[client_id] = [
            req_time
            for req_time in self._requests[client_id]
            if req_time > window_start
        ]

        # Check limit
        if len(self._requests[client_id]) >= self.max_requests:
            return False

        # Record this request
        self._requests[client_id].append(now)
        return True
