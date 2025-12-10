"""Shared dependencies for FastAPI application.

This module provides dependency injection functions for FastAPI endpoints.
These dependencies are used to access core services like search, databases, and connectors.
"""

from functools import lru_cache
from typing import Annotated

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential
from fastapi import Depends
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..indexing.graph_builder import GraphBuilder
from ..ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector
from ..search.hybrid_search import HybridSearchEngine
from .services.resource_service import ResourceService
from .services.terraform_service import TerraformService
from .services.git_service import GitService


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Azure OpenAI settings
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    azure_openai_api_version: str = Field(
        default="2024-02-01", description="Azure OpenAI API version"
    )
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-large", description="Embedding model deployment name"
    )
    azure_openai_chat_deployment: str = Field(
        default="gpt-4", description="Chat model deployment name"
    )

    # Azure AI Search settings
    azure_search_endpoint: str = Field(..., description="Azure AI Search endpoint URL")
    azure_search_index_name: str = Field(
        default="infra-rag-index", description="Search index name"
    )

    # Cosmos DB settings
    cosmos_db_endpoint: str = Field(..., description="Cosmos DB endpoint URL")
    cosmos_db_database: str = Field(
        default="infra-rag", description="Cosmos DB database name"
    )
    cosmos_db_container: str = Field(
        default="documents", description="Cosmos DB container name"
    )
    cosmos_db_gremlin_endpoint: str = Field(
        ..., description="Cosmos DB Gremlin endpoint URL (documents.azure.com format)"
    )
    cosmos_db_gremlin_database: str = Field(
        default="graph", description="Cosmos DB Gremlin database name"
    )
    cosmos_db_gremlin_graph: str = Field(
        default="infrastructure", description="Cosmos DB Gremlin graph/collection name"
    )
    cosmos_db_gremlin_key: str = Field(
        ..., description="Cosmos DB Gremlin account key for authentication"
    )

    # Service Bus settings (for ingestion)
    service_bus_namespace: str | None = Field(
        default=None, description="Service Bus namespace"
    )
    service_bus_queue: str = Field(
        default="ingestion-jobs", description="Service Bus queue name"
    )

    # Azure region (must be Canada East or Canada Central)
    azure_region: str = Field(
        default="canadaeast",
        description="Azure region for resources (canadaeast or canadacentral)",
    )

    # API settings
    api_version: str = Field(default="1.0.0", description="API version")
    api_title: str = Field(default="Infra-Aware RAG API", description="API title")
    api_description: str = Field(
        default="API for querying Azure infrastructure and Terraform IaC",
        description="API description",
    )

    # Application Insights settings
    applicationinsights_connection_string: str | None = Field(
        default=None,
        description="Application Insights connection string for telemetry",
    )

    # CORS settings
    cors_origins: list[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = Field(
        default=True, description="Allow credentials in CORS"
    )

    # Authentication settings (optional for MVP)
    azure_ad_tenant_id: str | None = Field(
        default=None, description="Azure AD tenant ID for authentication"
    )
    azure_ad_client_id: str | None = Field(
        default=None, description="Azure AD client ID for authentication"
    )

    # Rate limiting settings
    rate_limit_per_minute: int = Field(
        default=60, description="Requests per minute per user"
    )
    rate_limit_per_hour: int = Field(
        default=1000, description="Requests per hour per user"
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


# Global service instances (initialized during lifespan)
_services: dict[str, any] = {}


async def init_services(settings: Settings) -> None:
    """Initialize application services.

    Called during FastAPI lifespan startup.
    """
    # Initialize Azure credential
    credential = DefaultAzureCredential()

    # Initialize Cosmos DB client
    cosmos_client = CosmosClient(
        url=settings.cosmos_db_endpoint,
        credential=credential,
    )
    _services["cosmos_client"] = cosmos_client

    # Initialize Azure Resource Graph connector
    arg_connector = AzureResourceGraphConnector(credential=credential)
    _services["arg_connector"] = arg_connector

    # Initialize search engine
    search_engine = HybridSearchEngine(
        search_endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=credential,
        openai_endpoint=settings.azure_openai_endpoint,
        embedding_deployment=settings.azure_openai_embedding_deployment,
        api_version=settings.azure_openai_api_version,
    )
    _services["search_engine"] = search_engine

    # Initialize graph builder
    graph_builder = GraphBuilder(
        endpoint=settings.cosmos_db_gremlin_endpoint,
        database=settings.cosmos_db_gremlin_database,
        graph=settings.cosmos_db_gremlin_graph,
        key=settings.cosmos_db_gremlin_key,
    )
    _services["graph_builder"] = graph_builder

    # Initialize resource service
    resource_service = ResourceService(
        cosmos_client=cosmos_client,
        database_name=settings.cosmos_db_database,
        container_name=settings.cosmos_db_container,
        arg_connector=arg_connector,
    )
    _services["resource_service"] = resource_service

    # Initialize Terraform service
    terraform_service = TerraformService(
        cosmos_client=cosmos_client,
        database_name=settings.cosmos_db_database,
        container_name=settings.cosmos_db_container,
    )
    _services["terraform_service"] = terraform_service

    # Initialize Git service
    git_service = GitService(
        cosmos_client=cosmos_client,
        database_name=settings.cosmos_db_database,
        container_name=settings.cosmos_db_container,
    )
    _services["git_service"] = git_service

    # Initialize Application Insights (if configured)
    if settings.applicationinsights_connection_string:
        from .middleware.app_insights import init_app_insights

        init_app_insights(settings.applicationinsights_connection_string)


async def cleanup_services() -> None:
    """Cleanup application services.

    Called during FastAPI lifespan shutdown.
    """
    # Close Cosmos DB client
    if "cosmos_client" in _services:
        await _services["cosmos_client"].close()

    # Clear services
    _services.clear()


def get_search_engine() -> HybridSearchEngine:
    """Get the hybrid search engine instance."""
    if "search_engine" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["search_engine"]


def get_graph_builder() -> GraphBuilder:
    """Get the graph builder instance."""
    if "graph_builder" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["graph_builder"]


def get_cosmos_client() -> CosmosClient:
    """Get the Cosmos DB client instance."""
    if "cosmos_client" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["cosmos_client"]


def get_arg_connector() -> AzureResourceGraphConnector:
    """Get the Azure Resource Graph connector instance."""
    if "arg_connector" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["arg_connector"]


def get_resource_service() -> ResourceService:
    """Get the resource service instance."""
    if "resource_service" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["resource_service"]


def get_terraform_service() -> TerraformService:
    """Get the Terraform service instance."""
    if "terraform_service" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["terraform_service"]


def get_git_service() -> GitService:
    """Get the Git service instance."""
    if "git_service" not in _services:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services["git_service"]


# Type aliases for dependency injection
SearchEngineDep = Annotated[HybridSearchEngine, Depends(get_search_engine)]
GraphBuilderDep = Annotated[GraphBuilder, Depends(get_graph_builder)]
CosmosClientDep = Annotated[CosmosClient, Depends(get_cosmos_client)]
ARGConnectorDep = Annotated[AzureResourceGraphConnector, Depends(get_arg_connector)]
ResourceServiceDep = Annotated[ResourceService, Depends(get_resource_service)]
TerraformServiceDep = Annotated[TerraformService, Depends(get_terraform_service)]
GitServiceDep = Annotated[GitService, Depends(get_git_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
