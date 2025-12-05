"""Data models for indexing and chunking."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A chunk of text extracted from a document for embedding.

    Chunks are created by breaking down documents into smaller, semantically
    meaningful pieces that can be embedded and searched.
    """

    # Identity
    chunk_id: str  # Unique identifier: "{doc_id}:chunk:{index}"
    doc_id: str  # Source document ID
    doc_type: str  # Type of source document (azure_resource, terraform_resource, etc.)

    # Content
    text: str  # The chunk text to be embedded
    heading: str | None = None  # Optional heading/title for the chunk

    # Metadata
    chunk_index: int  # Position in the document (0-based)
    total_chunks: int  # Total number of chunks in the document

    # Source information
    source_file: str | None = None  # File path if applicable
    source_location: str | None = None  # Location within source (line numbers, etc.)

    # Semantic metadata
    resource_type: str | None = None  # Azure resource type, Terraform type, etc.
    resource_name: str | None = None  # Resource name
    tags: dict[str, str] = Field(default_factory=dict)  # Key-value tags/labels

    # Additional structured data
    properties: dict[str, Any] = Field(default_factory=dict)  # Type-specific properties

    # Embedding data
    token_count: int | None = None  # Token count for text
    embedding: list[float] | None = None  # Vector embedding
    embedding_model: str | None = None  # Model used for embedding

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def __str__(self) -> str:
        """String representation."""
        preview = self.text[:100] + "..." if len(self.text) > 100 else self.text
        return f"Chunk({self.chunk_id}): {preview}"

    def to_search_document(self) -> dict[str, Any]:
        """Convert chunk to Azure AI Search document.

        Returns:
            Dictionary suitable for indexing in Azure AI Search
        """
        import json

        doc = {
            "id": self.chunk_id,
            "content": self.text,
            "doc_type": self.doc_type,
        }

        # Add embedding if present
        if self.embedding:
            doc["embedding"] = self.embedding

        # Add optional fields
        if self.resource_type:
            doc["resource_type"] = self.resource_type
        if self.resource_name:
            doc["resource_name"] = self.resource_name
        if self.source_file:
            doc["file_path"] = self.source_file

        # Add tags as JSON string
        if self.tags:
            doc["tags"] = json.dumps(self.tags)

        # Add properties fields if they match search schema
        if self.properties:
            # Azure resource fields
            if "subscription_id" in self.properties:
                doc["subscription_id"] = self.properties["subscription_id"]
            if "resource_group" in self.properties:
                doc["resource_group"] = self.properties["resource_group"]
            if "location" in self.properties:
                doc["location"] = self.properties["location"]
            if "resource_id" in self.properties:
                doc["resource_id"] = self.properties["resource_id"]

            # Terraform fields
            if "provider" in self.properties:
                doc["provider"] = self.properties["provider"]
            if "address" in self.properties:
                doc["address"] = self.properties["address"]
            if "repo_url" in self.properties:
                doc["repo_url"] = self.properties["repo_url"]
            if "branch" in self.properties:
                doc["branch"] = self.properties["branch"]
            if "azure_resource_id" in self.properties:
                doc["azure_resource_id"] = self.properties["azure_resource_id"]

            # Git fields
            if "sha" in self.properties:
                doc["sha"] = self.properties["sha"]
            if "author_name" in self.properties:
                doc["author_name"] = self.properties["author_name"]
            if "author_email" in self.properties:
                doc["author_email"] = self.properties["author_email"]
            if "commit_date" in self.properties:
                doc["commit_date"] = self.properties["commit_date"]
            if "has_terraform_changes" in self.properties:
                doc["has_terraform_changes"] = self.properties["has_terraform_changes"]

            # Plan fields
            if "plan_id" in self.properties:
                doc["plan_id"] = self.properties["plan_id"]
            if "action" in self.properties:
                doc["action"] = self.properties["action"]

        return doc
