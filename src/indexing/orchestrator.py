"""Indexing orchestration for processing documents through chunking, embedding, and indexing."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents import SearchClient

from src.indexing.chunkers import (
    AzureResourceChunker,
    GitCommitChunker,
    TerraformPlanChunker,
    TerraformResourceChunker,
    TerraformStateChunker,
)
from src.indexing.embeddings import EmbeddingPipeline
from src.indexing.graph_builder import GraphBuilder
from src.indexing.indexer import SearchIndexer
from src.indexing.models import Chunk
from src.models.documents import (
    AzureResourceDocument,
    GitCommitDocument,
    TerraformPlanDocument,
    TerraformResourceDocument,
    TerraformStateDocument,
)

logger = logging.getLogger(__name__)


class IndexingStats:
    """Statistics for an indexing run."""

    def __init__(self):
        self.documents_processed = 0
        self.chunks_created = 0
        self.chunks_embedded = 0
        self.chunks_indexed = 0
        self.graph_vertices_added = 0
        self.graph_edges_added = 0
        self.errors = []
        self.start_time = datetime.now(UTC)
        self.end_time: datetime | None = None

    def record_error(self, doc_id: str, error: str):
        """Record an error for a document."""
        self.errors.append({"doc_id": doc_id, "error": error, "timestamp": datetime.now(UTC).isoformat()})

    def finalize(self):
        """Mark the indexing run as complete."""
        self.end_time = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        duration = (
            (self.end_time - self.start_time).total_seconds()
            if self.end_time
            else (datetime.now(UTC) - self.start_time).total_seconds()
        )
        return {
            "documents_processed": self.documents_processed,
            "chunks_created": self.chunks_created,
            "chunks_embedded": self.chunks_embedded,
            "chunks_indexed": self.chunks_indexed,
            "graph_vertices_added": self.graph_vertices_added,
            "graph_edges_added": self.graph_edges_added,
            "error_count": len(self.errors),
            "errors": self.errors,
            "duration_seconds": round(duration, 2),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class IndexingOrchestrator:
    """Orchestrates the indexing pipeline: chunking → embedding → indexing + graph.

    This orchestrator processes documents from Cosmos DB through the complete
    indexing pipeline:
    1. Chunk documents based on type
    2. Generate embeddings for chunks
    3. Upload chunks to Azure AI Search
    4. Populate graph database with relationships
    """

    def __init__(
        self,
        cosmos_client: CosmosClient,
        cosmos_database: str,
        cosmos_container: str,
        search_indexer: SearchIndexer,
        embedding_pipeline: EmbeddingPipeline,
        graph_builder: GraphBuilder,
        batch_size: int = 50,
    ):
        """Initialize indexing orchestrator.

        Args:
            cosmos_client: Cosmos DB client for reading documents
            cosmos_database: Database name
            cosmos_container: Container name for documents
            search_indexer: SearchIndexer for uploading to Azure AI Search
            embedding_pipeline: Pipeline for generating embeddings
            graph_builder: Graph database builder
            batch_size: Number of documents to process in each batch
        """
        self.cosmos_client = cosmos_client
        self.cosmos_database = cosmos_database
        self.cosmos_container = cosmos_container
        self.embedding_pipeline = embedding_pipeline
        self.graph_builder = graph_builder
        self.batch_size = batch_size

        # Store indexer
        self.indexer = search_indexer

        # Initialize chunkers
        self.azure_chunker = AzureResourceChunker()
        self.terraform_resource_chunker = TerraformResourceChunker()
        self.terraform_state_chunker = TerraformStateChunker()
        self.terraform_plan_chunker = TerraformPlanChunker()
        self.git_chunker = GitCommitChunker()

        # Get container client
        self.container = self.cosmos_client.get_database_client(cosmos_database).get_container_client(
            cosmos_container
        )

        # Track processed documents for incremental indexing
        self.processed_docs: set[str] = set()

    async def index_document(self, document: dict[str, Any]) -> IndexingStats:
        """Index a single document through the complete pipeline.

        Args:
            document: Document dictionary from Cosmos DB

        Returns:
            IndexingStats with results
        """
        stats = IndexingStats()

        try:
            # Convert to appropriate document model
            doc_type = document.get("doc_type")
            doc_id = document.get("id")

            if not doc_type or not doc_id:
                stats.record_error(doc_id or "unknown", "Missing doc_type or id field")
                stats.finalize()
                return stats

            logger.info(f"Processing document {doc_id} (type: {doc_type})")

            # Chunk the document
            chunks = await self._chunk_document(document, doc_type)
            stats.chunks_created = len(chunks)

            if not chunks:
                logger.warning(f"No chunks created for document {doc_id}")
                stats.documents_processed = 1
                stats.finalize()
                return stats

            # Generate embeddings
            embedded_chunks = []
            async for chunk in self.embedding_pipeline.embed_chunks(chunks):
                embedded_chunks.append(chunk)
            stats.chunks_embedded = len(embedded_chunks)

            # Index chunks
            index_results = self.indexer.index_chunks(iter(embedded_chunks))
            stats.chunks_indexed = index_results["succeeded"]

            if index_results["failed"] > 0:
                for error in index_results["errors"]:
                    stats.record_error(doc_id, f"Indexing error: {error}")

            # Populate graph database
            await self._populate_graph(document, doc_type)
            stats.graph_vertices_added = 1  # At least one vertex per document

            stats.documents_processed = 1
            logger.info(f"Successfully processed document {doc_id}: {stats.chunks_created} chunks, {stats.chunks_indexed} indexed")

        except Exception as e:
            logger.error(f"Error processing document {document.get('id', 'unknown')}: {e}", exc_info=True)
            stats.record_error(document.get("id", "unknown"), str(e))

        stats.finalize()
        return stats

    async def index_documents(self, documents: list[dict[str, Any]]) -> IndexingStats:
        """Index multiple documents in batch.

        Args:
            documents: List of document dictionaries

        Returns:
            Aggregated IndexingStats
        """
        stats = IndexingStats()

        for document in documents:
            doc_stats = await self.index_document(document)

            # Aggregate stats
            stats.documents_processed += doc_stats.documents_processed
            stats.chunks_created += doc_stats.chunks_created
            stats.chunks_embedded += doc_stats.chunks_embedded
            stats.chunks_indexed += doc_stats.chunks_indexed
            stats.graph_vertices_added += doc_stats.graph_vertices_added
            stats.graph_edges_added += doc_stats.graph_edges_added
            stats.errors.extend(doc_stats.errors)

        stats.finalize()
        return stats

    async def index_all_documents(
        self,
        doc_types: list[str] | None = None,
        since: datetime | None = None,
        incremental: bool = True,
    ) -> IndexingStats:
        """Index all documents from Cosmos DB.

        Args:
            doc_types: Filter to specific document types (e.g., ["azure_resource"])
            since: Only process documents modified since this time
            incremental: If True, skip documents that have already been processed

        Returns:
            IndexingStats with results
        """
        stats = IndexingStats()

        logger.info(f"Starting full index: doc_types={doc_types}, since={since}, incremental={incremental}")

        try:
            # Build query
            query = "SELECT * FROM c"
            conditions = []

            if doc_types:
                type_conditions = " OR ".join([f"c.doc_type = '{dt}'" for dt in doc_types])
                conditions.append(f"({type_conditions})")

            if since:
                conditions.append(f"c._ts >= {int(since.timestamp())}")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            # Query documents
            documents = []
            async for item in self.container.query_items(query=query, enable_cross_partition_query=True):
                doc_id = item.get("id")

                # Skip if incremental and already processed
                if incremental and doc_id in self.processed_docs:
                    logger.debug(f"Skipping already-processed document {doc_id}")
                    continue

                documents.append(item)

                # Process in batches
                if len(documents) >= self.batch_size:
                    batch_stats = await self.index_documents(documents)

                    # Aggregate stats
                    stats.documents_processed += batch_stats.documents_processed
                    stats.chunks_created += batch_stats.chunks_created
                    stats.chunks_embedded += batch_stats.chunks_embedded
                    stats.chunks_indexed += batch_stats.chunks_indexed
                    stats.graph_vertices_added += batch_stats.graph_vertices_added
                    stats.graph_edges_added += batch_stats.graph_edges_added
                    stats.errors.extend(batch_stats.errors)

                    # Mark as processed
                    if incremental:
                        for doc in documents:
                            self.processed_docs.add(doc.get("id"))

                    documents = []

            # Process remaining documents
            if documents:
                batch_stats = await self.index_documents(documents)

                stats.documents_processed += batch_stats.documents_processed
                stats.chunks_created += batch_stats.chunks_created
                stats.chunks_embedded += batch_stats.chunks_embedded
                stats.chunks_indexed += batch_stats.chunks_indexed
                stats.graph_vertices_added += batch_stats.graph_vertices_added
                stats.graph_edges_added += batch_stats.graph_edges_added
                stats.errors.extend(batch_stats.errors)

                if incremental:
                    for doc in documents:
                        self.processed_docs.add(doc.get("id"))

        except Exception as e:
            logger.error(f"Error during full index: {e}", exc_info=True)
            stats.record_error("batch", str(e))

        stats.finalize()

        logger.info(
            f"Indexing complete: {stats.documents_processed} docs, "
            f"{stats.chunks_indexed} chunks indexed, "
            f"{len(stats.errors)} errors, "
            f"{stats.to_dict()['duration_seconds']}s"
        )

        return stats

    async def _chunk_document(self, document: dict[str, Any], doc_type: str) -> list[Chunk]:
        """Chunk a document based on its type.

        Args:
            document: Document dictionary
            doc_type: Document type

        Returns:
            List of chunks
        """
        try:
            if doc_type == "azure_resource":
                doc = AzureResourceDocument.model_validate(document)
                return self.azure_chunker.chunk(doc)
            elif doc_type == "terraform_resource":
                doc = TerraformResourceDocument.model_validate(document)
                return self.terraform_resource_chunker.chunk(doc)
            elif doc_type == "terraform_state":
                doc = TerraformStateDocument.model_validate(document)
                return self.terraform_state_chunker.chunk(doc)
            elif doc_type == "terraform_plan":
                doc = TerraformPlanDocument.model_validate(document)
                return self.terraform_plan_chunker.chunk(doc)
            elif doc_type == "git_commit":
                doc = GitCommitDocument.model_validate(document)
                return self.git_chunker.chunk(doc)
            else:
                logger.warning(f"Unknown document type: {doc_type}")
                return []
        except Exception as e:
            logger.error(f"Error chunking document: {e}", exc_info=True)
            return []

    async def _populate_graph(self, document: dict[str, Any], doc_type: str):
        """Populate graph database with document relationships.

        Args:
            document: Document dictionary
            doc_type: Document type
        """
        try:
            if doc_type == "azure_resource":
                # Add subscription
                sub_id = document.get("subscription_id")
                sub_name = document.get("subscription_name", "Unknown")
                tenant_id = document.get("tenant_id", "")
                if sub_id:
                    self.graph_builder.add_subscription(sub_id, sub_name, tenant_id)

                # Add resource group
                rg_id = f"/subscriptions/{sub_id}/resourceGroups/{document.get('resource_group')}"
                self.graph_builder.add_resource_group(
                    rg_id=rg_id,
                    name=document.get("resource_group", ""),
                    sub_id=sub_id,
                    location=document.get("location", ""),
                )

                # Add resource
                self.graph_builder.add_azure_resource(
                    {
                        "id": document.get("id"),
                        "type": document.get("type"),
                        "name": document.get("name"),
                        "location": document.get("location"),
                        "subscription_id": sub_id,
                        "resource_group": document.get("resource_group"),
                    }
                )

            elif doc_type == "terraform_resource":
                # Add terraform resource
                self.graph_builder.add_terraform_resource(
                    address=document.get("address", ""),
                    resource_type=document.get("type", ""),
                    file_path=document.get("file_path", ""),
                    repo_url=document.get("repo_url"),
                )

                # Link to Azure resource if azure_resource_id is present
                azure_resource_id = document.get("azure_resource_id")
                if azure_resource_id:
                    self.graph_builder.link_terraform_to_azure(
                        tf_address=document.get("address", ""),
                        azure_resource_id=azure_resource_id,
                    )

        except Exception as e:
            logger.error(f"Error populating graph: {e}", exc_info=True)

    def reset_processed_docs(self):
        """Reset the set of processed documents (for full re-indexing)."""
        self.processed_docs.clear()
        logger.info("Reset processed documents set")

    def get_processed_count(self) -> int:
        """Get the number of processed documents.

        Returns:
            Count of processed documents
        """
        return len(self.processed_docs)
