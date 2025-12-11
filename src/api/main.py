"""FastAPI application for Infra-Aware RAG API.

This module defines the main FastAPI application with:
- Lifespan management for service initialization/cleanup
- Health and readiness check endpoints
- CORS middleware configuration
- OpenAPI documentation
- Router registration (routers will be added as they're implemented)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .dependencies import cleanup_services, get_settings, init_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Manages initialization and cleanup of services:
    - Startup: Initialize Azure clients, search engine, graph builder
    - Shutdown: Close connections and cleanup resources
    """
    # Startup
    settings = get_settings()
    await init_services(settings)

    yield

    # Shutdown
    await cleanup_services()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This function is separated to allow for easier testing and to avoid
    loading settings at module level.
    """
    # Get settings for app metadata
    try:
        settings = get_settings()
        title = settings.api_title
        description = settings.api_description
        version = settings.api_version
        cors_origins = settings.cors_origins
        cors_allow_credentials = settings.cors_allow_credentials
    except Exception:
        # Use defaults if settings can't be loaded (e.g., in tests)
        title = "Infra-Aware RAG API"
        description = "API for querying Azure infrastructure and Terraform IaC"
        version = "1.0.0"
        cors_origins = ["*"]
        cors_allow_credentials = True

    # Create FastAPI application
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


# Create the application instance
app = create_app()

# Note: Middleware is implemented in src/api/middleware/ but not enabled by default.
# Enable in production by uncommenting below and providing required settings:
# from .middleware import AuthMiddleware, RateLimitMiddleware, LoggingMiddleware
# app.add_middleware(AuthMiddleware, tenant_id=settings.azure_ad_tenant_id, client_id=settings.azure_ad_client_id)
# app.add_middleware(RateLimitMiddleware)
# app.add_middleware(LoggingMiddleware)


# Health check endpoints
@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Basic health check endpoint. Returns 200 if the service is running.",
)
async def health_check():
    """Health check endpoint.

    Returns a simple status indicating the service is running.
    This endpoint does not check dependencies.
    """
    return {"status": "healthy"}


@app.get(
    "/ready",
    tags=["health"],
    summary="Readiness check",
    description="Readiness check endpoint. Returns 200 if the service is ready to handle requests.",
)
async def readiness_check():
    """Readiness check endpoint.

    Checks that required services are initialized and ready.
    This is used by orchestration platforms (Kubernetes, Azure Container Apps)
    to determine if the service can receive traffic.
    """
    from .dependencies import _services

    # Check which services are initialized
    dependencies = {
        "search_engine": "ready" if "search_engine" in _services else "not_initialized",
        "cosmos_db": "ready" if "cosmos_client" in _services else "not_initialized",
        "graph_db": "ready" if "graph_builder" in _services else "not_initialized",
        "resource_service": "ready" if "resource_service" in _services else "not_initialized",
        "terraform_service": "ready" if "terraform_service" in _services else "not_initialized",
        "git_service": "ready" if "git_service" in _services else "not_initialized",
        "orchestration_engine": "ready" if "orchestration_engine" in _services else "not_initialized",
        "conversation_manager": "ready" if "conversation_manager" in _services else "not_initialized",
    }

    # Check if all required services are ready
    all_ready = all(status == "ready" for status in dependencies.values())

    return {
        "status": "ready" if all_ready else "not_ready",
        "dependencies": dependencies,
    }


# Register API routers
from .routers import search, resources, terraform, git, tools, conversations

app.include_router(search.router, prefix="/api/v1")
app.include_router(resources.router, prefix="/api/v1")
app.include_router(terraform.router, prefix="/api/v1")
app.include_router(git.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
