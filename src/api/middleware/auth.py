"""Authentication middleware for Azure AD integration.

This middleware validates JWT tokens from Azure AD and extracts user information.
It supports both user authentication and service-to-service authentication via managed identities.
"""

import time
from typing import Any

import httpx
from fastapi import HTTPException, Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate requests using Azure AD (Entra ID) tokens.

    This middleware:
    1. Validates JWT tokens against Azure AD
    2. Caches JWKS (JSON Web Key Set) for performance
    3. Extracts user information and adds it to request state
    4. Exempts certain paths from authentication (health checks, docs)
    """

    # Paths that don't require authentication
    EXEMPT_PATHS = [
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]

    def __init__(
        self,
        app,
        tenant_id: str | None = None,
        client_id: str | None = None,
        enabled: bool = True,
    ):
        """Initialize the authentication middleware.

        Args:
            app: The FastAPI application
            tenant_id: Azure AD tenant ID (if None, auth is disabled)
            client_id: Azure AD client/application ID (if None, auth is disabled)
            enabled: Whether authentication is enabled (default: True)
        """
        super().__init__(app)
        self.enabled = enabled and tenant_id is not None and client_id is not None
        self.tenant_id = tenant_id
        self.client_id = client_id

        if self.enabled:
            self.jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
            self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        else:
            self.jwks_url = None
            self.issuer = None

        # JWKS cache
        self._jwks: dict[str, Any] | None = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: float = 3600  # Cache for 1 hour

    async def dispatch(self, request: Request, call_next):
        """Process the request and validate authentication.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            The response from the next handler

        Raises:
            HTTPException: If authentication fails
        """
        # Skip auth for exempt paths
        if any(request.url.path.startswith(p) for p in self.EXEMPT_PATHS):
            return await call_next(request)

        # If auth is disabled, allow all requests
        if not self.enabled:
            # Add mock user for development
            request.state.user = {
                "sub": "dev-user",
                "name": "Development User",
                "email": "dev@example.com",
                "groups": [],
            }
            return await call_next(request)

        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.split(" ")[1]

        try:
            # Validate token and extract user info
            payload = await self._validate_token(token)

            # Add user info to request state
            request.state.user = {
                "sub": payload.get("sub"),
                "oid": payload.get("oid"),  # Object ID
                "tid": payload.get("tid"),  # Tenant ID
                "name": payload.get("name"),
                "email": payload.get("preferred_username") or payload.get("upn"),
                "groups": payload.get("groups", []),
                "roles": payload.get("roles", []),
            }

        except JWTError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Authentication error: {str(e)}",
            )

        return await call_next(request)

    async def _validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token against Azure AD.

        Args:
            token: The JWT token to validate

        Returns:
            The decoded token payload

        Raises:
            JWTError: If token validation fails
        """
        # Get JWKS (with caching)
        jwks = await self._get_jwks()

        # Decode and validate token
        # Note: python-jose handles JWKS key selection automatically
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=self.client_id,
            issuer=self.issuer,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iat": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
            },
        )

        return payload

    async def _get_jwks(self) -> dict[str, Any]:
        """Get JWKS from Azure AD with caching.

        Returns:
            The JWKS dictionary

        Raises:
            Exception: If JWKS fetch fails
        """
        now = time.time()

        # Return cached JWKS if still valid
        if self._jwks and (now - self._jwks_cache_time) < self._jwks_cache_ttl:
            return self._jwks

        # Fetch fresh JWKS
        async with httpx.AsyncClient() as client:
            response = await client.get(self.jwks_url, timeout=10.0)
            response.raise_for_status()
            self._jwks = response.json()
            self._jwks_cache_time = now

        return self._jwks


def get_current_user(request: Request) -> dict[str, Any]:
    """Get the current authenticated user from the request.

    This is a dependency that can be injected into route handlers.

    Args:
        request: The FastAPI request

    Returns:
        User information dictionary

    Raises:
        HTTPException: If user is not authenticated

    Example:
        ```python
        @router.get("/me")
        async def get_me(user = Depends(get_current_user)):
            return {"name": user["name"], "email": user["email"]}
        ```
    """
    if not hasattr(request.state, "user"):
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )
    return request.state.user


def require_role(required_role: str):
    """Dependency to require a specific Azure AD role.

    Args:
        required_role: The role name required

    Returns:
        A dependency function that validates the role

    Example:
        ```python
        @router.post("/admin/action")
        async def admin_action(user = Depends(require_role("Admin"))):
            # Only users with "Admin" role can access
            ...
        ```
    """

    def check_role(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        if required_role not in user.get("roles", []):
            raise HTTPException(
                status_code=403,
                detail=f"Required role '{required_role}' not found",
            )
        return user

    return check_role


def require_group(required_group: str):
    """Dependency to require membership in a specific Azure AD group.

    Args:
        required_group: The group ID or name required

    Returns:
        A dependency function that validates group membership

    Example:
        ```python
        @router.get("/resources")
        async def list_resources(user = Depends(require_group("InfraTeam"))):
            # Only users in "InfraTeam" group can access
            ...
        ```
    """

    def check_group(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        if required_group not in user.get("groups", []):
            raise HTTPException(
                status_code=403,
                detail=f"Required group '{required_group}' membership not found",
            )
        return user

    return check_group
