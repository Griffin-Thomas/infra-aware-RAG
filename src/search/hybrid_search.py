"""Hybrid search engine combining vector, keyword, and graph queries."""

import logging
from typing import Any

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from src.indexing.embeddings import EmbeddingPipeline
from src.indexing.graph_builder import GraphBuilder
from src.search.models import HybridSearchResults, SearchResult

logger = logging.getLogger(__name__)


class HybridSearchEngine:
    """Hybrid search combining vector similarity, keyword search, and graph traversal.

    Search modes:
    - vector: Pure semantic similarity search using embeddings
    - keyword: Traditional full-text search with semantic ranking
    - hybrid: Combined vector + keyword search for best results
    - graph: Graph-based expansion for relationship-aware search
    """

    def __init__(
        self,
        search_client: SearchClient,
        graph_builder: GraphBuilder,
        embedding_pipeline: EmbeddingPipeline,
    ):
        """Initialize hybrid search engine.

        Args:
            search_client: Azure AI Search client
            graph_builder: Graph database for relationship queries
            embedding_pipeline: Pipeline for generating query embeddings
        """
        self.search_client = search_client
        self.graph_builder = graph_builder
        self.embedding_pipeline = embedding_pipeline

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        doc_types: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        top: int = 10,
        include_facets: bool = False,
    ) -> HybridSearchResults:
        """Execute a search query.

        Args:
            query: Natural language query string
            mode: Search mode - "vector", "keyword", or "hybrid" (default)
            doc_types: Filter to specific document types (e.g., ["azure_resource", "terraform_resource"])
            filters: Additional OData filters (e.g., {"location": "canadaeast"})
            top: Maximum number of results to return
            include_facets: Include facet counts in results

        Returns:
            HybridSearchResults with matching documents

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in ("vector", "keyword", "hybrid"):
            raise ValueError(f"Invalid search mode: {mode}. Must be 'vector', 'keyword', or 'hybrid'")

        # Build filter expression
        filter_expr = self._build_filter(doc_types, filters)

        logger.info(f"Executing {mode} search for query: '{query}' (top={top})")

        if mode == "vector":
            return await self._vector_search(query, filter_expr, top, include_facets)
        elif mode == "keyword":
            return await self._keyword_search(query, filter_expr, top, include_facets)
        else:  # hybrid
            return await self._hybrid_search(query, filter_expr, top, include_facets)

    async def _vector_search(
        self,
        query: str,
        filter_expr: str | None,
        top: int,
        include_facets: bool,
    ) -> HybridSearchResults:
        """Execute pure vector similarity search.

        Args:
            query: Query string
            filter_expr: OData filter expression
            top: Number of results
            include_facets: Include facet counts

        Returns:
            Search results ordered by vector similarity
        """
        # Generate query embedding
        query_embedding = await self.embedding_pipeline.embed_single(query)

        # Create vector query
        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top,
            fields="embedding",
        )

        # Execute search
        results = self.search_client.search(
            search_text=None,  # No keyword search
            vector_queries=[vector_query],
            filter=filter_expr,
            top=top,
            include_total_count=True,
            facets=["doc_type", "resource_type", "location"] if include_facets else None,
        )

        return self._process_results(results, include_facets)

    async def _keyword_search(
        self,
        query: str,
        filter_expr: str | None,
        top: int,
        include_facets: bool,
    ) -> HybridSearchResults:
        """Execute pure keyword search with semantic ranking.

        Args:
            query: Query string
            filter_expr: OData filter expression
            top: Number of results
            include_facets: Include facet counts

        Returns:
            Search results ordered by keyword relevance
        """
        # Execute search
        results = self.search_client.search(
            search_text=query,
            query_type="semantic",
            semantic_configuration_name="semantic-config",
            filter=filter_expr,
            top=top,
            include_total_count=True,
            highlight_fields="content",
            facets=["doc_type", "resource_type", "location"] if include_facets else None,
        )

        return self._process_results(results, include_facets)

    async def _hybrid_search(
        self,
        query: str,
        filter_expr: str | None,
        top: int,
        include_facets: bool,
    ) -> HybridSearchResults:
        """Execute hybrid search combining vector and keyword search.

        Args:
            query: Query string
            filter_expr: OData filter expression
            top: Number of results
            include_facets: Include facet counts

        Returns:
            Search results using hybrid ranking (vector + keyword)
        """
        # Generate query embedding
        query_embedding = await self.embedding_pipeline.embed_single(query)

        # Create vector query
        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top * 2,  # Over-fetch for better fusion
            fields="embedding",
        )

        # Execute hybrid search
        results = self.search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="semantic-config",
            filter=filter_expr,
            top=top,
            include_total_count=True,
            highlight_fields="content",
            facets=["doc_type", "resource_type", "location"] if include_facets else None,
        )

        return self._process_results(results, include_facets)

    def _build_filter(
        self,
        doc_types: list[str] | None,
        filters: dict[str, Any] | None,
    ) -> str | None:
        """Build OData filter expression from parameters.

        Args:
            doc_types: Document types to filter
            filters: Additional field filters

        Returns:
            OData filter expression or None if no filters
        """
        parts = []

        # Add doc_type filter
        if doc_types:
            type_filter = " or ".join(f"doc_type eq '{t}'" for t in doc_types)
            parts.append(f"({type_filter})")

        # Add custom filters
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    # OR condition for multiple values
                    val_filter = " or ".join(f"{key} eq '{v}'" for v in value)
                    parts.append(f"({val_filter})")
                elif isinstance(value, bool):
                    # Boolean values need lowercase
                    parts.append(f"{key} eq {str(value).lower()}")
                elif value is None:
                    # Null check
                    parts.append(f"{key} eq null")
                else:
                    # String/number equality
                    parts.append(f"{key} eq '{value}'")

        return " and ".join(parts) if parts else None

    def _process_results(
        self,
        results,
        include_facets: bool,
    ) -> HybridSearchResults:
        """Process raw Azure AI Search results into SearchResult objects.

        Args:
            results: Raw search results from Azure AI Search
            include_facets: Whether facets were requested

        Returns:
            Processed HybridSearchResults
        """
        search_results = []

        for result in results:
            # Extract highlights if present
            highlights = None
            if "@search.highlights" in result:
                highlights_dict = result.get("@search.highlights", {})
                if "content" in highlights_dict:
                    highlights = highlights_dict["content"]

            # Build metadata dict (exclude special fields)
            metadata = {
                k: v
                for k, v in result.items()
                if k not in ("id", "content", "doc_type", "embedding") and not k.startswith("@search")
            }

            search_results.append(
                SearchResult(
                    id=result.get("id", ""),
                    score=result.get("@search.score", 0.0),
                    content=result.get("content", ""),
                    doc_type=result.get("doc_type", "unknown"),
                    metadata=metadata,
                    highlights=highlights,
                )
            )

        # Extract facets if requested
        facets = None
        if include_facets and hasattr(results, "get_facets"):
            facets = results.get_facets()

        # Get total count
        total_count = len(search_results)
        if hasattr(results, "get_count"):
            count_result = results.get_count()
            if count_result is not None:
                total_count = count_result

        logger.info(f"Processed {len(search_results)} results (total: {total_count})")

        return HybridSearchResults(
            results=search_results,
            total_count=total_count,
            facets=facets,
        )

    async def search_with_graph_expansion(
        self,
        query: str,
        top: int = 10,
        expand_depth: int = 1,
        doc_types: list[str] | None = None,
    ) -> HybridSearchResults:
        """Search with graph-based expansion for related resources.

        First executes a hybrid search to find relevant resources, then uses the
        graph database to find related resources (dependencies, Terraform, etc.)
        and includes them in the results.

        Args:
            query: Natural language query
            top: Number of initial results
            expand_depth: Graph traversal depth (1-3 recommended)
            doc_types: Filter initial search to document types

        Returns:
            HybridSearchResults with both direct matches and related resources
        """
        logger.info(f"Executing graph-expanded search for '{query}' (depth={expand_depth})")

        # Initial hybrid search
        initial_results = await self.search(
            query=query,
            mode="hybrid",
            doc_types=doc_types or ["azure_resource"],
            top=top,
        )

        if not initial_results.results:
            return initial_results

        # Expand via graph for Azure resources
        expanded_ids = set()
        for result in initial_results.results:
            resource_id = result.metadata.get("resource_id")
            if resource_id:
                try:
                    # Find related resources via graph
                    related = self.graph_builder.find_dependencies(
                        resource_id=resource_id,
                        direction="both",
                        depth=expand_depth,
                    )

                    # Extract resource IDs from paths
                    for path in related:
                        if isinstance(path, (list, tuple)):
                            for vertex in path:
                                if isinstance(vertex, dict) and "id" in vertex:
                                    expanded_ids.add(vertex["id"])
                        elif isinstance(path, dict) and "id" in path:
                            expanded_ids.add(path["id"])

                except Exception as e:
                    logger.warning(f"Failed to expand graph for {resource_id}: {e}")

        # Fetch expanded resources from search index
        if expanded_ids:
            # Limit to 50 expanded resources to avoid huge result sets
            expanded_ids_list = list(expanded_ids)[:50]
            expanded_filter = " or ".join(
                f"resource_id eq '{rid}'" for rid in expanded_ids_list
            )

            try:
                expanded_results = self.search_client.search(
                    search_text="*",  # Match all
                    filter=expanded_filter,
                    top=50,
                )

                # Merge results (keeping originals first with higher scores)
                existing_ids = {r.id for r in initial_results.results}
                for result in expanded_results:
                    if result.get("id") not in existing_ids:
                        initial_results.results.append(
                            SearchResult(
                                id=result.get("id", ""),
                                score=0.5,  # Lower score for graph-expanded results
                                content=result.get("content", ""),
                                doc_type=result.get("doc_type", "unknown"),
                                metadata={
                                    k: v
                                    for k, v in result.items()
                                    if k not in ("id", "content", "doc_type", "embedding")
                                    and not k.startswith("@search")
                                },
                            )
                        )

                logger.info(f"Expanded results from {len(initial_results.results) - len(existing_ids)} to {len(initial_results.results)} documents")

            except Exception as e:
                logger.error(f"Failed to fetch expanded resources: {e}")

        return initial_results

    def close(self):
        """Close search client and cleanup resources."""
        if self.search_client:
            self.search_client.close()
