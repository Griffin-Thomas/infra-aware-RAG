"""Search API request and response models."""

from pydantic import BaseModel, Field
from typing import Any


class SearchRequest(BaseModel):
    """Search request model."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query string")
    mode: str = Field(
        default="hybrid",
        pattern="^(vector|keyword|hybrid)$",
        description="Search mode: vector (semantic), keyword (full-text), or hybrid (combined)",
    )
    doc_types: list[str] | None = Field(
        default=None,
        description="Filter by document types (azure_resource, terraform_resource, git_commit, terraform_plan)",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Additional OData filters (e.g., {'location': 'canadaeast'})",
    )
    top: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return")
    include_facets: bool = Field(default=False, description="Include facet counts in response")


class SearchResult(BaseModel):
    """Individual search result."""

    id: str = Field(..., description="Unique document identifier")
    score: float = Field(..., description="Relevance score")
    content: str = Field(..., description="Document content or summary")
    doc_type: str = Field(..., description="Document type (azure_resource, terraform_resource, etc.)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    highlights: list[str] | None = Field(default=None, description="Highlighted text snippets")


class SearchResponse(BaseModel):
    """Search response model."""

    results: list[SearchResult] = Field(default_factory=list, description="List of search results")
    total_count: int = Field(..., description="Total number of matching documents")
    facets: dict[str, Any] | None = Field(default=None, description="Facet counts by category")


class GraphExpandRequest(BaseModel):
    """Request model for graph-expanded search."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query string")
    top: int = Field(default=10, ge=1, le=100, description="Maximum number of initial results")
    expand_depth: int = Field(default=1, ge=1, le=3, description="Graph traversal depth (1-3)")
    doc_types: list[str] | None = Field(
        default=None,
        description="Filter initial search by document types",
    )
