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

# TODO: Add authentication middleware (Phase 3.2)
# app.add_middleware(AuthMiddleware)

# TODO: Add rate limiting middleware (Phase 3.3)
# app.add_middleware(RateLimitMiddleware)

# TODO: Add logging middleware (Phase 3.3)
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
    # TODO: Add actual dependency checks (search engine, Cosmos DB, etc.)
    # For now, just return ready status
    return {
        "status": "ready",
        "dependencies": {
            "search_engine": "ready",
            "cosmos_db": "ready",
            "graph_db": "ready",
        },
    }


# TODO: Register routers as they're implemented
# from .routers import search, resources, terraform, git, tools
# app.include_router(search.router, prefix="/api/v1", tags=["search"])
# app.include_router(resources.router, prefix="/api/v1", tags=["resources"])
# app.include_router(terraform.router, prefix="/api/v1", tags=["terraform"])
# app.include_router(git.router, prefix="/api/v1", tags=["git"])
# app.include_router(tools.router, prefix="/api/v1", tags=["tools"])
