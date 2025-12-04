# Phase 2: Indexing and Search

## Overview

This phase transforms the raw data ingested in Phase 1 into searchable indexes that power the RAG system. We will:

1. **Chunk** documents into appropriately sized pieces for embedding
2. **Generate embeddings** using Azure OpenAI's text-embedding models
3. **Build a vector index** in Azure AI Search for semantic search
4. **Create a graph model** in Cosmos DB (Gremlin API) for relationship traversal
5. **Implement hybrid search** combining vector, keyword, and graph queries

By the end of this phase, we will have a robust search infrastructure that can find relevant infrastructure context for any natural language query.

---

## Scope

### In Scope
- Document chunking strategies for different content types
- Embedding generation pipeline with batching
- Azure AI Search index with vector and keyword fields
- Graph database schema in Cosmos DB Gremlin
- Relationship extraction and graph population
- Hybrid search API combining all search modalities
- Search relevance tuning and testing

### Out of Scope (Future Phases)
- Real-time index updates (streaming)
- Custom fine-tuned embeddings
- Cross-encoder re-ranking
- Query expansion/reformulation
- Multi-language support

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Search API                                        │
│               (Hybrid Search: Vector + Keyword + Graph)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                │                │
                    ▼                ▼                ▼
         ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
         │ Azure AI     │  │  Azure AI Search │  │  Cosmos DB   │
         │ Search       │  │  (Keyword/Filter)│  │  (Gremlin)   │
         │ (Vector)     │  │                  │  │              │
         └──────────────┘  └──────────────────┘  └──────────────┘
                    ▲                ▲                ▲
                    │                │                │
                    └────────────────┼────────────────┘
                                     │
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Indexing Pipeline                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │    Chunker      │  │   Embedder      │  │   Graph Builder             │  │
│  │  (Split docs)   │  │  (Azure OpenAI) │  │  (Extract relationships)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     ▲
                                     │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Document Store (Cosmos DB)                            │
│         Raw documents from Phase 1 ingestion pipeline                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Decisions

### Embedding Model

**Decision:** Azure OpenAI `text-embedding-3-large` with 3072 dimensions (configurable down to 256).

**Rationale:**
- State-of-the-art performance on retrieval benchmarks
- Native Azure integration with managed identity
- Dimension reduction available for cost/performance tradeoff
- 8191 token input limit handles most chunks

**Alternatives Considered:**
- `text-embedding-3-small`: Lower cost but reduced quality
- Cohere Embed v3: Good alternative but adds vendor dependency
- sentence-transformers (local): No API costs but requires GPU hosting

**Configuration:**
```python
EMBEDDING_CONFIG = {
    "model": "text-embedding-3-large",
    "dimensions": 1536,  # Reduced from 3072 for cost/perf balance
    "max_tokens": 8191,
    "batch_size": 16,    # API batch limit
}
```

### Vector Store

**Decision:** Azure AI Search with vector search capability.

**Rationale:**
- Integrated with Azure ecosystem
- Supports both vector and keyword search in same index
- Built-in semantic ranking
- Filtering on metadata fields
- Managed service (no infrastructure)

**Alternatives Considered:**
- Pinecone: Excellent but adds vendor/cost
- Weaviate: Good OSS option but requires self-hosting
- pgvector: Simple but limited scale
- Qdrant: Good performance but requires self-hosting

### Graph Database

**Decision:** Azure Cosmos DB with Gremlin API.

**Rationale:**
- Managed graph database service
- Gremlin is a standard graph query language
- Same Cosmos DB account as document store
- Global distribution available
- Integrates with Azure RBAC

**Alternatives Considered:**
- Neo4j: Industry leader but separate service to manage
- Amazon Neptune: Good but AWS-specific
- TigerGraph: Powerful but complex

---

## Chunking Strategy

Different document types require different chunking approaches to preserve context and maximize retrieval quality.

### Azure Resource Documents

**Strategy:** Single chunk per resource with structured fields.

**Rationale:** Resources are self-contained units; splitting loses context.

```python
class AzureResourceChunker:
    """Chunker for Azure resource documents."""

    def chunk(self, doc: AzureResourceDocument) -> list[Chunk]:
        """Create a single chunk for the resource."""
        text = self._build_chunk_text(doc)

        return [Chunk(
            id=f"azure:{doc.id}",
            text=text,
            doc_type="azure_resource",
            metadata={
                "resource_id": doc.id,
                "resource_type": doc.type,
                "resource_group": doc.resource_group,
                "subscription_id": doc.subscription_id,
                "location": doc.location,
                "tags": doc.tags,
            },
        )]

    def _build_chunk_text(self, doc: AzureResourceDocument) -> str:
        """Build searchable text for the resource."""
        lines = [
            f"# Azure Resource: {doc.name}",
            f"",
            f"**Type:** {doc.type}",
            f"**Resource Group:** {doc.resource_group}",
            f"**Subscription:** {doc.subscription_name}",
            f"**Location:** {doc.location}",
        ]

        if doc.tags:
            lines.append(f"**Tags:** {', '.join(f'{k}={v}' for k, v in doc.tags.items())}")

        if doc.sku:
            lines.append(f"**SKU:** {doc.sku.get('name', 'N/A')} ({doc.sku.get('tier', 'N/A')})")

        # Add key properties based on resource type
        lines.extend(self._extract_key_properties(doc))

        return "\n".join(lines)

    def _extract_key_properties(self, doc: AzureResourceDocument) -> list[str]:
        """Extract type-specific properties for the chunk."""
        props = doc.properties
        lines = []

        # Virtual Machines
        if "virtualMachines" in doc.type:
            if "hardwareProfile" in props:
                lines.append(f"**VM Size:** {props['hardwareProfile'].get('vmSize')}")
            if "storageProfile" in props:
                os_disk = props["storageProfile"].get("osDisk", {})
                lines.append(f"**OS Type:** {os_disk.get('osType')}")
            if "networkProfile" in props:
                nics = props["networkProfile"].get("networkInterfaces", [])
                lines.append(f"**NICs:** {len(nics)}")

        # Storage Accounts
        elif "storageAccounts" in doc.type:
            lines.append(f"**Kind:** {doc.kind}")
            lines.append(f"**Access Tier:** {props.get('accessTier', 'N/A')}")
            lines.append(f"**HTTPS Only:** {props.get('supportsHttpsTrafficOnly', False)}")

        # More type-specific extractors...

        return lines
```

### Terraform Resource Documents

**Strategy:** One chunk per resource block, including full source code.

```python
class TerraformResourceChunker:
    """Chunker for Terraform resource documents."""

    MAX_SOURCE_LINES = 100  # Truncate very large resources

    def chunk(self, doc: TerraformResourceDocument) -> list[Chunk]:
        """Create a chunk for the Terraform resource."""
        text = self._build_chunk_text(doc)

        return [Chunk(
            id=f"terraform:{doc.id}",
            text=text,
            doc_type="terraform_resource",
            metadata={
                "address": doc.address,
                "resource_type": doc.type,
                "provider": doc.provider,
                "file_path": doc.file_path,
                "line_number": doc.line_number,
                "repo_url": doc.repo_url,
                "branch": doc.branch,
                "azure_resource_id": doc.azure_resource_id,
            },
        )]

    def _build_chunk_text(self, doc: TerraformResourceDocument) -> str:
        """Build searchable text for the Terraform resource."""
        source = doc.source_code
        if source.count("\n") > self.MAX_SOURCE_LINES:
            source = "\n".join(source.split("\n")[:self.MAX_SOURCE_LINES])
            source += "\n# ... (truncated)"

        return f"""# Terraform Resource: {doc.address}

**Type:** {doc.type}
**Provider:** {doc.provider}
**File:** {doc.file_path}:{doc.line_number}
**Repository:** {doc.repo_url} ({doc.branch})

## Source Code

```hcl
{source}
```

## Dependencies

{self._format_dependencies(doc)}
"""

    def _format_dependencies(self, doc: TerraformResourceDocument) -> str:
        """Format resource dependencies."""
        deps = doc.dependencies + doc.implicit_dependencies
        if not deps:
            return "None"
        return "\n".join(f"- {dep}" for dep in deps)
```

### Git Commit Documents

**Strategy:** One chunk per commit with summary and file list.

```python
class GitCommitChunker:
    """Chunker for Git commit documents."""

    MAX_FILES = 50  # Limit files in chunk

    def chunk(self, doc: GitCommitDocument) -> list[Chunk]:
        """Create a chunk for the Git commit."""
        text = self._build_chunk_text(doc)

        return [Chunk(
            id=f"git:{doc.id}",
            text=text,
            doc_type="git_commit",
            metadata={
                "sha": doc.sha,
                "repo_url": doc.repo_url,
                "branch": doc.branch,
                "author_name": doc.author_name,
                "author_email": doc.author_email,
                "commit_date": doc.commit_date.isoformat(),
                "has_terraform_changes": doc.has_terraform_changes,
            },
        )]

    def _build_chunk_text(self, doc: GitCommitDocument) -> str:
        """Build searchable text for the commit."""
        files = doc.files_changed[:self.MAX_FILES]
        files_str = "\n".join(
            f"- {f['path']} ({f['change_type']})"
            for f in files
        )
        if len(doc.files_changed) > self.MAX_FILES:
            files_str += f"\n- ... and {len(doc.files_changed) - self.MAX_FILES} more files"

        tf_section = ""
        if doc.has_terraform_changes:
            tf_section = f"""
## Terraform Changes

Changed Terraform files:
{chr(10).join(f'- {f}' for f in doc.terraform_files_changed)}
"""

        return f"""# Git Commit: {doc.short_sha}

**Repository:** {doc.repo_url} ({doc.branch})
**Author:** {doc.author_name} <{doc.author_email}>
**Date:** {doc.commit_date.isoformat()}

## Commit Message

{doc.message}

## Files Changed (+{doc.total_additions}/-{doc.total_deletions})

{files_str}
{tf_section}
"""
```

### Terraform Plan Documents

**Strategy:** Multiple chunks - one summary chunk plus one chunk per significant change.

```python
class TerraformPlanChunker:
    """Chunker for Terraform plan documents."""

    def chunk(self, doc: TerraformPlanDocument) -> list[Chunk]:
        """Create chunks for the Terraform plan."""
        chunks = []

        # Summary chunk
        chunks.append(self._create_summary_chunk(doc))

        # Individual change chunks for significant changes
        for change in doc.changes:
            if change.action != "no-op":
                chunks.append(self._create_change_chunk(doc, change))

        return chunks

    def _create_summary_chunk(self, doc: TerraformPlanDocument) -> Chunk:
        """Create a summary chunk for the plan."""
        text = f"""# Terraform Plan Summary

**Repository:** {doc.repo_url} ({doc.branch})
**Commit:** {doc.commit_sha}
**Directory:** {doc.terraform_dir}
**Generated:** {doc.plan_timestamp.isoformat()}

## Change Summary

- **Add:** {doc.total_add} resources
- **Change:** {doc.total_change} resources
- **Destroy:** {doc.total_destroy} resources

## Resources Affected

{self._list_changes(doc.changes)}
"""

        return Chunk(
            id=f"plan-summary:{doc.id}",
            text=text,
            doc_type="terraform_plan_summary",
            metadata={
                "plan_id": doc.id,
                "repo_url": doc.repo_url,
                "commit_sha": doc.commit_sha,
                "total_add": doc.total_add,
                "total_change": doc.total_change,
                "total_destroy": doc.total_destroy,
            },
        )

    def _create_change_chunk(self, doc: TerraformPlanDocument, change: PlannedChange) -> Chunk:
        """Create a chunk for an individual change."""
        text = f"""# Terraform Plan: {change.action.upper()} {change.address}

**Action:** {change.action}
**Resource Type:** {change.resource_type}
**Provider:** {change.provider}

## Changes

{self._format_change_details(change)}
"""

        return Chunk(
            id=f"plan-change:{doc.id}:{change.address}",
            text=text,
            doc_type="terraform_plan_change",
            metadata={
                "plan_id": doc.id,
                "address": change.address,
                "action": change.action,
                "resource_type": change.resource_type,
            },
        )

    def _list_changes(self, changes: list[PlannedChange]) -> str:
        """List all changes in the plan."""
        return "\n".join(
            f"- [{c.action}] {c.address}"
            for c in changes
            if c.action != "no-op"
        )

    def _format_change_details(self, change: PlannedChange) -> str:
        """Format the attribute-level changes."""
        if change.action == "create":
            return f"New resource will be created with {len(change.after or {})} attributes."
        elif change.action == "delete":
            return "Resource will be destroyed."
        elif change.action in ("update", "replace"):
            attrs = change.changed_attributes
            return f"Attributes changing: {', '.join(attrs)}"
        return "No changes."
```

---

## Chunk Data Model

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class Chunk:
    """A chunk ready for embedding and indexing."""

    id: str                     # Unique chunk ID
    text: str                   # Text content for embedding
    doc_type: str               # Type of source document
    metadata: dict[str, Any]    # Structured metadata for filtering

    # Populated during embedding
    embedding: list[float] | None = None
    embedding_model: str | None = None

    # Token count (for cost tracking)
    token_count: int | None = None

    def to_search_document(self) -> dict:
        """Convert to Azure AI Search document format."""
        return {
            "id": self.id,
            "content": self.text,
            "doc_type": self.doc_type,
            "embedding": self.embedding,
            **self.metadata,
        }
```

---

## Embedding Pipeline

```python
# src/indexing/embeddings.py

from openai import AsyncAzureOpenAI
from typing import AsyncIterator
import asyncio
import tiktoken

class EmbeddingPipeline:
    """Pipeline for generating embeddings from chunks."""

    def __init__(
        self,
        azure_endpoint: str,
        api_key: str | None = None,  # Uses DefaultAzureCredential if None
        model: str = "text-embedding-3-large",
        dimensions: int = 1536,
        batch_size: int = 16,
        max_retries: int = 3,
    ):
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Initialize client
        if api_key:
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version="2024-02-01",
            )
        else:
            from azure.identity.aio import DefaultAzureCredential
            credential = DefaultAzureCredential()
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                azure_ad_token_provider=credential.get_token,
                api_version="2024-02-01",
            )

        # Token counter
        self.encoding = tiktoken.get_encoding("cl100k_base")

    async def embed_chunks(
        self,
        chunks: list[Chunk],
    ) -> AsyncIterator[Chunk]:
        """
        Generate embeddings for chunks.

        Yields chunks with embeddings populated.
        """
        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i + self.batch_size]

            # Prepare texts
            texts = []
            for chunk in batch:
                # Count tokens and truncate if needed
                tokens = self.encoding.encode(chunk.text)
                if len(tokens) > 8191:
                    chunk.text = self.encoding.decode(tokens[:8000])
                    tokens = tokens[:8000]

                chunk.token_count = len(tokens)
                texts.append(chunk.text)

            # Generate embeddings
            embeddings = await self._embed_with_retry(texts)

            # Yield chunks with embeddings
            for chunk, embedding in zip(batch, embeddings):
                chunk.embedding = embedding
                chunk.embedding_model = self.model
                yield chunk

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings with retry logic."""
        for attempt in range(self.max_retries):
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                    dimensions=self.dimensions,
                )
                return [item.embedding for item in response.data]

            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                print(f"Embedding failed, retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=[text],
            dimensions=self.dimensions,
        )
        return response.data[0].embedding
```

---

## Azure AI Search Index

### Index Schema

```python
# src/indexing/search_index.py

from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
)

def create_infra_index() -> SearchIndex:
    """Create the search index schema for infrastructure documents."""

    fields = [
        # Core fields
        SearchField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
        ),
        SearchField(
            name="content",
            type=SearchFieldDataType.String,
            searchable=True,
            analyzer_name="en.microsoft",
        ),
        SearchField(
            name="doc_type",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),

        # Vector field
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,
            vector_search_profile_name="embedding-profile",
        ),

        # Azure resource fields
        SearchField(name="resource_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="resource_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="resource_group", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="subscription_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="location", type=SearchFieldDataType.String, filterable=True, facetable=True),

        # Terraform fields
        SearchField(name="address", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="provider", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="file_path", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="repo_url", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="branch", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="azure_resource_id", type=SearchFieldDataType.String, filterable=True),

        # Git fields
        SearchField(name="sha", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="author_name", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="author_email", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="commit_date", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SearchField(name="has_terraform_changes", type=SearchFieldDataType.Boolean, filterable=True),

        # Plan fields
        SearchField(name="plan_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="action", type=SearchFieldDataType.String, filterable=True, facetable=True),

        # Tags (stored as JSON string for flexibility)
        SearchField(name="tags", type=SearchFieldDataType.String, searchable=True),
    ]

    # Vector search configuration
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-algorithm",
                parameters={
                    "m": 4,
                    "efConstruction": 400,
                    "efSearch": 500,
                    "metric": "cosine",
                },
            ),
        ],
        profiles=[
            VectorSearchProfile(
                name="embedding-profile",
                algorithm_configuration_name="hnsw-algorithm",
            ),
        ],
    )

    # Semantic configuration for re-ranking
    semantic_config = SemanticConfiguration(
        name="semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="content")],
        ),
    )

    return SearchIndex(
        name="infra-index",
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
    )


class SearchIndexManager:
    """Manages the Azure AI Search index."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        index_name: str = "infra-index",
    ):
        self.endpoint = endpoint
        self.index_name = index_name

        if api_key:
            self.index_client = SearchIndexClient(endpoint, AzureKeyCredential(api_key))
        else:
            from azure.identity import DefaultAzureCredential
            self.index_client = SearchIndexClient(endpoint, DefaultAzureCredential())

    def create_or_update_index(self):
        """Create or update the search index."""
        index = create_infra_index()
        self.index_client.create_or_update_index(index)

    def delete_index(self):
        """Delete the search index."""
        self.index_client.delete_index(self.index_name)
```

### Index Population

```python
# src/indexing/indexer.py

from azure.search.documents import SearchClient
from azure.search.documents.models import IndexingResult
from typing import Iterator

class SearchIndexer:
    """Populates the Azure AI Search index with chunks."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        index_name: str = "infra-index",
        batch_size: int = 100,
    ):
        self.endpoint = endpoint
        self.index_name = index_name
        self.batch_size = batch_size

        if api_key:
            self.search_client = SearchClient(
                endpoint, index_name, AzureKeyCredential(api_key)
            )
        else:
            from azure.identity import DefaultAzureCredential
            self.search_client = SearchClient(
                endpoint, index_name, DefaultAzureCredential()
            )

    def index_chunks(self, chunks: Iterator[Chunk]) -> dict:
        """
        Index chunks in batches.

        Returns statistics about the indexing operation.
        """
        stats = {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
        }

        batch = []
        for chunk in chunks:
            batch.append(chunk.to_search_document())

            if len(batch) >= self.batch_size:
                self._upload_batch(batch, stats)
                batch = []

        # Upload remaining
        if batch:
            self._upload_batch(batch, stats)

        return stats

    def _upload_batch(self, batch: list[dict], stats: dict):
        """Upload a batch of documents."""
        try:
            results = self.search_client.upload_documents(batch)
            for result in results:
                stats["total"] += 1
                if result.succeeded:
                    stats["succeeded"] += 1
                else:
                    stats["failed"] += 1
                    stats["errors"].append({
                        "key": result.key,
                        "error": result.error_message,
                    })
        except Exception as e:
            stats["failed"] += len(batch)
            stats["errors"].append({"error": str(e)})

    def delete_documents(self, ids: list[str]):
        """Delete documents by ID."""
        self.search_client.delete_documents([{"id": id} for id in ids])
```

---

## Graph Database Schema

### Graph Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GRAPH SCHEMA                                    │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────┐
                    │    Subscription     │
                    │  - id               │
                    │  - name             │
                    │  - tenant_id        │
                    └──────────┬──────────┘
                               │ contains
                               ▼
                    ┌─────────────────────┐
                    │   ResourceGroup     │
                    │  - id               │
                    │  - name             │
                    │  - location         │
                    └──────────┬──────────┘
                               │ contains
                               ▼
    ┌────────────────────────────────────────────────────────┐
    │                    AzureResource                        │
    │  - id (Azure Resource ID)                               │
    │  - type                                                 │
    │  - name                                                 │
    │  - location                                             │
    │  - sku                                                  │
    └────┬─────────────────────────────────────────────┬─────┘
         │                                             │
         │ managed_by                                  │ depends_on
         ▼                                             ▼
    ┌─────────────────────┐                   ┌─────────────────────┐
    │  TerraformResource  │                   │   AzureResource     │
    │  - address          │                   │   (other resources) │
    │  - type             │                   └─────────────────────┘
    │  - file_path        │
    └──────────┬──────────┘
               │ defined_in
               ▼
    ┌─────────────────────┐
    │   TerraformFile     │
    │  - path             │
    │  - repo_url         │
    │  - branch           │
    └──────────┬──────────┘
               │ part_of
               ▼
    ┌─────────────────────┐
    │     GitRepo         │──────── has_commit ────────▶ ┌─────────────────────┐
    │  - url              │                              │    GitCommit        │
    │  - default_branch   │                              │  - sha              │
    └─────────────────────┘                              │  - message          │
                                                         │  - author           │
                                                         │  - date             │
                                                         └──────────┬──────────┘
                                                                    │ modified
                                                                    ▼
                                                         ┌─────────────────────┐
                                                         │   TerraformFile     │
                                                         └─────────────────────┘
```

### Graph Population

```python
# src/indexing/graph_builder.py

from gremlin_python.driver import client, serializer
from gremlin_python.process.traversal import T
from typing import Any

class GraphBuilder:
    """Builds and populates the infrastructure graph in Cosmos DB Gremlin."""

    def __init__(
        self,
        endpoint: str,
        database: str,
        graph: str,
        key: str,
    ):
        self.endpoint = endpoint
        self.database = database
        self.graph = graph

        # Build Gremlin endpoint
        gremlin_endpoint = endpoint.replace("https://", "wss://").replace(
            ".documents.azure.com:443/",
            ".gremlin.cosmos.azure.com:443/"
        )

        self.client = client.Client(
            gremlin_endpoint,
            "g",
            username=f"/dbs/{database}/colls/{graph}",
            password=key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )

    def add_subscription(self, sub_id: str, name: str, tenant_id: str):
        """Add a subscription vertex."""
        query = """
        g.V().has('subscription', 'id', sub_id).fold()
        .coalesce(
            unfold(),
            addV('subscription').property('id', sub_id)
        )
        .property('name', name)
        .property('tenant_id', tenant_id)
        """
        self.client.submit(query, {"sub_id": sub_id, "name": name, "tenant_id": tenant_id})

    def add_resource_group(self, rg_id: str, name: str, sub_id: str, location: str):
        """Add a resource group vertex with edge to subscription."""
        # Add vertex
        self.client.submit("""
        g.V().has('resource_group', 'id', rg_id).fold()
        .coalesce(
            unfold(),
            addV('resource_group').property('id', rg_id)
        )
        .property('name', name)
        .property('location', location)
        """, {"rg_id": rg_id, "name": name, "location": location})

        # Add edge to subscription
        self.client.submit("""
        g.V().has('subscription', 'id', sub_id)
        .coalesce(
            outE('contains').where(inV().has('resource_group', 'id', rg_id)),
            addE('contains').to(g.V().has('resource_group', 'id', rg_id))
        )
        """, {"sub_id": sub_id, "rg_id": rg_id})

    def add_azure_resource(self, resource: dict):
        """Add an Azure resource vertex."""
        self.client.submit("""
        g.V().has('azure_resource', 'id', res_id).fold()
        .coalesce(
            unfold(),
            addV('azure_resource').property('id', res_id)
        )
        .property('type', res_type)
        .property('name', name)
        .property('location', location)
        """, {
            "res_id": resource["id"],
            "res_type": resource["type"],
            "name": resource["name"],
            "location": resource["location"],
        })

        # Add edge to resource group
        rg_id = f"/subscriptions/{resource['subscription_id']}/resourceGroups/{resource['resource_group']}"
        self.client.submit("""
        g.V().has('resource_group', 'id', rg_id)
        .coalesce(
            outE('contains').where(inV().has('azure_resource', 'id', res_id)),
            addE('contains').to(g.V().has('azure_resource', 'id', res_id))
        )
        """, {"rg_id": rg_id, "res_id": resource["id"]})

    def add_resource_dependency(self, from_id: str, to_id: str, dep_type: str = "depends_on"):
        """Add a dependency edge between resources."""
        self.client.submit("""
        g.V().has('azure_resource', 'id', from_id)
        .coalesce(
            outE(dep_type).where(inV().has('azure_resource', 'id', to_id)),
            addE(dep_type).to(g.V().has('azure_resource', 'id', to_id))
        )
        """, {"from_id": from_id, "to_id": to_id, "dep_type": dep_type})

    def link_terraform_to_azure(self, tf_address: str, azure_id: str):
        """Link a Terraform resource to an Azure resource."""
        self.client.submit("""
        g.V().has('terraform_resource', 'address', tf_addr)
        .coalesce(
            outE('manages').where(inV().has('azure_resource', 'id', azure_id)),
            addE('manages').to(g.V().has('azure_resource', 'id', azure_id))
        )
        """, {"tf_addr": tf_address, "azure_id": azure_id})

    def find_dependencies(self, resource_id: str, direction: str = "both", depth: int = 2) -> list:
        """Find resources connected to a given resource."""
        if direction == "in":
            query = f"g.V().has('azure_resource', 'id', res_id).repeat(inE().outV()).times({depth}).path()"
        elif direction == "out":
            query = f"g.V().has('azure_resource', 'id', res_id).repeat(outE().inV()).times({depth}).path()"
        else:
            query = f"g.V().has('azure_resource', 'id', res_id).repeat(bothE().otherV()).times({depth}).dedup().path()"

        results = self.client.submit(query, {"res_id": resource_id})
        return list(results)

    def find_terraform_for_resource(self, azure_id: str) -> list:
        """Find Terraform resources that manage an Azure resource."""
        query = """
        g.V().has('azure_resource', 'id', azure_id)
        .inE('manages').outV()
        .project('address', 'file_path', 'repo_url')
        .by('address').by('file_path').by('repo_url')
        """
        results = self.client.submit(query, {"azure_id": azure_id})
        return list(results)

    def close(self):
        """Close the Gremlin client."""
        self.client.close()
```

---

## Hybrid Search Implementation

```python
# src/search/hybrid_search.py

from dataclasses import dataclass
from typing import Any
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

@dataclass
class SearchResult:
    """A single search result."""
    id: str
    score: float
    content: str
    doc_type: str
    metadata: dict[str, Any]
    highlights: list[str] | None = None


@dataclass
class HybridSearchResults:
    """Results from hybrid search."""
    results: list[SearchResult]
    total_count: int
    facets: dict[str, list] | None = None


class HybridSearchEngine:
    """
    Hybrid search combining vector, keyword, and graph queries.

    Search modes:
    - vector: Semantic similarity search
    - keyword: Traditional full-text search
    - hybrid: Combined vector + keyword
    - graph: Graph traversal for related resources
    """

    def __init__(
        self,
        search_client: SearchClient,
        graph_builder: GraphBuilder,
        embedding_pipeline: EmbeddingPipeline,
    ):
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
        """
        Execute a search query.

        Args:
            query: Natural language query
            mode: Search mode (vector, keyword, hybrid)
            doc_types: Filter to specific document types
            filters: Additional filters
            top: Number of results to return
            include_facets: Include facet counts

        Returns:
            HybridSearchResults with matching documents
        """
        # Build filter expression
        filter_expr = self._build_filter(doc_types, filters)

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
        """Pure vector search."""
        # Generate query embedding
        query_embedding = await self.embedding_pipeline.embed_single(query)

        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top,
            fields="embedding",
        )

        results = self.search_client.search(
            search_text=None,
            vector_queries=[vector_query],
            filter=filter_expr,
            top=top,
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
        """Pure keyword search."""
        results = self.search_client.search(
            search_text=query,
            query_type="semantic",
            semantic_configuration_name="semantic-config",
            filter=filter_expr,
            top=top,
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
        """Combined vector + keyword search."""
        # Generate query embedding
        query_embedding = await self.embedding_pipeline.embed_single(query)

        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top * 2,  # Over-fetch for fusion
            fields="embedding",
        )

        results = self.search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="semantic-config",
            filter=filter_expr,
            top=top,
            highlight_fields="content",
            facets=["doc_type", "resource_type", "location"] if include_facets else None,
        )

        return self._process_results(results, include_facets)

    def _build_filter(
        self,
        doc_types: list[str] | None,
        filters: dict[str, Any] | None,
    ) -> str | None:
        """Build OData filter expression."""
        parts = []

        if doc_types:
            type_filter = " or ".join(f"doc_type eq '{t}'" for t in doc_types)
            parts.append(f"({type_filter})")

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    val_filter = " or ".join(f"{key} eq '{v}'" for v in value)
                    parts.append(f"({val_filter})")
                elif isinstance(value, bool):
                    parts.append(f"{key} eq {str(value).lower()}")
                else:
                    parts.append(f"{key} eq '{value}'")

        return " and ".join(parts) if parts else None

    def _process_results(
        self,
        results,
        include_facets: bool,
    ) -> HybridSearchResults:
        """Process raw search results."""
        search_results = []

        for result in results:
            search_results.append(SearchResult(
                id=result["id"],
                score=result["@search.score"],
                content=result["content"],
                doc_type=result["doc_type"],
                metadata={
                    k: v for k, v in result.items()
                    if k not in ("id", "content", "doc_type", "embedding", "@search.score")
                },
                highlights=result.get("@search.highlights", {}).get("content"),
            ))

        facets = None
        if include_facets and hasattr(results, "get_facets"):
            facets = results.get_facets()

        return HybridSearchResults(
            results=search_results,
            total_count=results.get_count() or len(search_results),
            facets=facets,
        )

    async def search_with_graph_expansion(
        self,
        query: str,
        top: int = 10,
        expand_depth: int = 1,
    ) -> HybridSearchResults:
        """
        Search with graph expansion.

        First finds relevant resources, then expands to related resources.
        """
        # Initial search
        initial_results = await self.search(
            query=query,
            mode="hybrid",
            doc_types=["azure_resource"],
            top=top,
        )

        # Expand via graph
        expanded_ids = set()
        for result in initial_results.results:
            if result.metadata.get("resource_id"):
                related = self.graph_builder.find_dependencies(
                    result.metadata["resource_id"],
                    depth=expand_depth,
                )
                for path in related:
                    for vertex in path:
                        if isinstance(vertex, dict) and "id" in vertex:
                            expanded_ids.add(vertex["id"])

        # Fetch expanded resources
        if expanded_ids:
            expanded_filter = " or ".join(
                f"resource_id eq '{id}'" for id in list(expanded_ids)[:50]
            )
            expanded_results = self.search_client.search(
                search_text="*",
                filter=expanded_filter,
                top=50,
            )

            # Merge results (keeping originals first)
            existing_ids = {r.id for r in initial_results.results}
            for result in expanded_results:
                if result["id"] not in existing_ids:
                    initial_results.results.append(SearchResult(
                        id=result["id"],
                        score=0.5,  # Lower score for expanded results
                        content=result["content"],
                        doc_type=result["doc_type"],
                        metadata={
                            k: v for k, v in result.items()
                            if k not in ("id", "content", "doc_type", "embedding")
                        },
                    ))

        return initial_results
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_chunking.py

import pytest
from src.indexing.chunkers import AzureResourceChunker, TerraformResourceChunker

class TestAzureResourceChunker:

    def test_chunk_vm_resource(self):
        """Test chunking a VM resource."""
        doc = AzureResourceDocument(
            id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            name="vm-1",
            type="Microsoft.Compute/virtualMachines",
            resource_group="rg-1",
            subscription_id="sub-1",
            subscription_name="Production",
            location="canadaeast",
            tags={"environment": "prod"},
            properties={
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
            }
        )

        chunker = AzureResourceChunker()
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        assert chunks[0].doc_type == "azure_resource"
        assert "vm-1" in chunks[0].text
        assert "Standard_D2s_v3" in chunks[0].text
        assert chunks[0].metadata["resource_type"] == "Microsoft.Compute/virtualMachines"


class TestTerraformResourceChunker:

    def test_chunk_terraform_resource(self):
        """Test chunking a Terraform resource."""
        doc = TerraformResourceDocument(
            id="github.com/org/repo:main:terraform/main.tf:azurerm_virtual_machine.main",
            address="azurerm_virtual_machine.main",
            type="azurerm_virtual_machine",
            name="main",
            file_path="terraform/main.tf",
            line_number=10,
            repo_url="https://github.com/org/repo",
            branch="main",
            provider="azurerm",
            source_code='''resource "azurerm_virtual_machine" "main" {
  name                = "my-vm"
  resource_group_name = azurerm_resource_group.main.name
}''',
            dependencies=["azurerm_resource_group.main"],
        )

        chunker = TerraformResourceChunker()
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        assert "azurerm_virtual_machine.main" in chunks[0].text
        assert "azurerm_resource_group.main" in chunks[0].text
```

### Integration Tests

```python
# tests/integration/test_search.py

import pytest
from src.search.hybrid_search import HybridSearchEngine

@pytest.mark.integration
@pytest.mark.asyncio
async def test_hybrid_search(search_engine):
    """Test hybrid search returns relevant results."""
    results = await search_engine.search(
        query="virtual machines in production",
        mode="hybrid",
        top=5,
    )

    assert results.total_count > 0
    assert all(r.score > 0 for r in results.results)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_filtered_search(search_engine):
    """Test search with filters for Canadian resources."""
    # All project resources must be in Canada East or Canada Central
    results = await search_engine.search(
        query="storage",
        mode="hybrid",
        doc_types=["azure_resource"],
        filters={"location": "canadaeast"},
        top=10,
    )

    assert all(r.metadata.get("location") == "canadaeast" for r in results.results)
    assert all(r.doc_type == "azure_resource" for r in results.results)
```

### End-to-End Tests

```python
# tests/e2e/test_indexing_pipeline.py

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_indexing_pipeline(e2e_config):
    """Test complete indexing from documents to searchable index."""
    # 1. Create test documents
    docs = [
        AzureResourceDocument(
            id="/subscriptions/test/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            name="test-vm",
            type="Microsoft.Compute/virtualMachines",
            # ... other fields
        ),
    ]

    # 2. Chunk documents
    chunker = AzureResourceChunker()
    chunks = []
    for doc in docs:
        chunks.extend(chunker.chunk(doc))

    # 3. Generate embeddings
    embedding_pipeline = EmbeddingPipeline(
        azure_endpoint=e2e_config["openai_endpoint"],
    )
    embedded_chunks = [c async for c in embedding_pipeline.embed_chunks(chunks)]

    # 4. Index chunks
    indexer = SearchIndexer(
        endpoint=e2e_config["search_endpoint"],
        index_name="test-index",
    )
    stats = indexer.index_chunks(iter(embedded_chunks))
    assert stats["failed"] == 0

    # 5. Search
    search_engine = HybridSearchEngine(...)
    results = await search_engine.search("test virtual machine")
    assert any("test-vm" in r.content for r in results.results)
```

---

## Demo Strategy

### Demo 1: Embedding Generation
**Goal:** Show that we can generate embeddings for infrastructure documents.

**Steps:**
1. Create sample Azure resource documents
2. Run through chunking pipeline
3. Generate embeddings
4. Display embedding dimensions and token counts

### Demo 2: Vector Search
**Goal:** Show semantic search finding relevant resources.

**Steps:**
1. Index sample infrastructure data
2. Query with natural language: "databases in production"
3. Show results ranked by relevance
4. Compare with keyword search results

### Demo 3: Graph Traversal
**Goal:** Show relationship-aware search.

**Steps:**
1. Populate graph with resources and dependencies
2. Query: "What depends on this virtual network?"
3. Traverse graph to find connected resources
4. Display relationship paths

### Demo 4: Hybrid Search
**Goal:** Show combined search capabilities.

**Steps:**
1. Query: "Show me the Terraform code for production storage accounts"
2. Vector search finds relevant resources
3. Graph links to Terraform definitions
4. Return combined results with source code

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Embedding API costs | High costs with large datasets | Batch processing; cache embeddings; use smaller dimensions |
| Embedding API rate limits | Indexing delays | Implement backoff; queue-based processing |
| Vector index size limits | Storage costs, query latency | Prune old data; dimension reduction |
| Graph query complexity | Timeouts on large graphs | Limit traversal depth; add timeouts; optimize queries |
| Search relevance issues | Poor user experience | Tuning; feedback collection; A/B testing |
| Index staleness | Stale search results | Show freshness indicators; real-time updates for critical data |

---

## Open Questions

1. **Embedding dimensions:** Should we use 3072 (full) or 1536 (reduced) dimensions?
2. **Chunk size:** What's the optimal chunk size for different document types?
3. **Graph complexity:** How deep should graph traversals go by default?
4. **Update strategy:** Incremental updates or full reindex on changes?
5. **Multi-tenancy:** Should different subscriptions have separate indexes?

---

## Task List

> **See [TASKS.md](../TASKS.md)** for the authoritative task list.
>
> Tasks for this phase are under **"Phase 2: Indexing & Search"** including:
> - 2.1 Azure Infrastructure for Indexing
> - 2.2 Chunking Pipeline
> - 2.3 Embedding Pipeline
> - 2.4 Azure AI Search Index
> - 2.5 Graph Database
> - 2.6 Hybrid Search Engine
> - 2.7 Indexing Pipeline Integration

---

## Dependencies

```
# requirements.txt (Phase 2 additions)

# Azure AI Search
azure-search-documents>=11.4.0

# Azure OpenAI
openai>=1.6.0

# Cosmos DB Gremlin
gremlinpython>=3.7.0

# Token counting
tiktoken>=0.5.0

# Async utilities
aiocache>=0.12.0
```

---

## Milestones

### Milestone 2.1: Embedding Pipeline (End of Week 4)
- Chunking implemented for all document types
- Embedding generation working
- Token counting and cost tracking
- Unit tests passing

### Milestone 2.2: Vector Index (End of Week 5)
- Azure AI Search index created
- Documents indexed with embeddings
- Vector search working
- Keyword and hybrid search working
- Filtering and faceting operational

### Milestone 2.3: Graph Database (End of Week 6)
- Graph schema implemented
- Relationships populated from ingested data
- Graph queries working
- Hybrid search with graph expansion
- Ready for Phase 3 (API Layer)
