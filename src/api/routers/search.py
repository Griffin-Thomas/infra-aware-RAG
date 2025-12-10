"""Search API router."""

import logging
from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_search_engine
from src.api.models.search import (
    SearchRequest,
    SearchResult,
    SearchResponse,
    GraphExpandRequest,
)
from src.search.hybrid_search import HybridSearchEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_engine: HybridSearchEngine = Depends(get_search_engine),
):
    """
    Search across infrastructure data.

    Supports multiple search modes:
    - **vector**: Semantic similarity search using embeddings
    - **keyword**: Traditional full-text search with semantic ranking
    - **hybrid**: Combined vector and keyword search (recommended)

    Filter by document types:
    - `azure_resource`: Azure resources from Resource Graph
    - `terraform_resource`: Terraform resource definitions
    - `git_commit`: Git commit history
    - `terraform_plan`: Terraform plan analysis

    Additional filters can be applied using the `filters` parameter.
    """
    try:
        logger.info(
            f"Search request: query='{request.query}', mode={request.mode}, "
            f"doc_types={request.doc_types}, top={request.top}"
        )

        results = await search_engine.search(
            query=request.query,
            mode=request.mode,
            doc_types=request.doc_types,
            filters=request.filters,
            top=request.top,
            include_facets=request.include_facets,
        )

        return SearchResponse(
            results=[
                SearchResult(
                    id=r.id,
                    score=r.score,
                    content=r.content,
                    doc_type=r.doc_type,
                    metadata=r.metadata,
                    highlights=r.highlights,
                )
                for r in results.results
            ],
            total_count=results.total_count,
            facets=results.facets,
        )
    except ValueError as e:
        # Invalid search mode or parameters
        logger.warning(f"Invalid search request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected errors
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed. Please try again later.")


@router.post("/expand", response_model=SearchResponse)
async def search_with_expansion(
    request: GraphExpandRequest,
    search_engine: HybridSearchEngine = Depends(get_search_engine),
):
    """
    Search with graph expansion.

    First performs a hybrid search, then expands results using
    the graph database to find related resources (dependencies,
    Terraform code, etc.).

    **Graph expansion** helps find:
    - Resource dependencies (e.g., VM -> VNet -> Subnet)
    - Terraform code managing Azure resources
    - Related resources in the same resource group
    - Historical changes from git commits

    **Depth levels:**
    - 1: Direct relationships (default)
    - 2: Second-degree relationships
    - 3: Third-degree relationships (may be slow)
    """
    try:
        logger.info(
            f"Graph-expanded search request: query='{request.query}', "
            f"depth={request.expand_depth}, top={request.top}"
        )

        results = await search_engine.search_with_graph_expansion(
            query=request.query,
            top=request.top,
            expand_depth=request.expand_depth,
            doc_types=request.doc_types,
        )

        return SearchResponse(
            results=[
                SearchResult(
                    id=r.id,
                    score=r.score,
                    content=r.content,
                    doc_type=r.doc_type,
                    metadata=r.metadata,
                    highlights=r.highlights,
                )
                for r in results.results
            ],
            total_count=results.total_count,
            facets=results.facets,
        )
    except Exception as e:
        logger.error(f"Graph-expanded search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Graph-expanded search failed. Please try again later.",
        )
