"""Chunkers for breaking documents into embeddable pieces."""

import json
import logging
from typing import Any

from src.indexing.models import Chunk
from src.models.documents import (
    AzureResourceDocument,
    GitCommitDocument,
    TerraformPlanDocument,
    TerraformResourceDocument,
    TerraformStateDocument,
)

logger = logging.getLogger(__name__)


class AzureResourceChunker:
    """Chunker for Azure Resource documents.

    Creates chunks that capture the resource configuration, properties,
    and type-specific metadata.
    """

    def __init__(self, max_chunk_size: int = 2000):
        """Initialize chunker.

        Args:
            max_chunk_size: Maximum characters per chunk
        """
        self.max_chunk_size = max_chunk_size

    def chunk(self, document: AzureResourceDocument) -> list[Chunk]:
        """Break an Azure resource document into chunks.

        Args:
            document: Azure resource document to chunk

        Returns:
            List of chunks
        """
        chunks = []

        # Main chunk: resource overview
        main_text = self._build_main_text(document)
        chunks.append(
            Chunk(
                chunk_id=f"{document.id}:chunk:0",
                doc_id=document.id,
                doc_type=document.doc_type,
                text=main_text,
                heading=f"{document.type}: {document.name}",
                chunk_index=0,
                total_chunks=1,  # Will update at end
                source_location=document.id,
                resource_type=document.type,
                resource_name=document.name,
                tags=document.tags,
                properties=self._extract_key_properties(document),
            )
        )

        # If properties are large, create additional chunks
        if document.properties and len(json.dumps(document.properties)) > self.max_chunk_size:
            property_chunks = self._chunk_properties(document)
            chunks.extend(property_chunks)

        # Update total_chunks
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _build_main_text(self, document: AzureResourceDocument) -> str:
        """Build the main text for a resource chunk."""
        lines = [
            f"Azure Resource: {document.type}",
            f"Name: {document.name}",
            f"Resource Group: {document.resource_group}",
            f"Location: {document.location}",
            f"Subscription: {document.subscription_name or document.subscription_id}",
        ]

        # Add tags if present
        if document.tags:
            lines.append(f"Tags: {', '.join(f'{k}={v}' for k, v in document.tags.items())}")

        # Add key properties
        key_props = self._extract_key_properties(document)
        if key_props:
            lines.append("\nKey Properties:")
            for key, value in key_props.items():
                lines.append(f"  {key}: {value}")

        # Add searchable text
        if document.searchable_text:
            lines.append("\n" + document.searchable_text)

        return "\n".join(lines)

    def _extract_key_properties(self, document: AzureResourceDocument) -> dict[str, Any]:
        """Extract key properties based on resource type."""
        if not document.properties:
            return {}

        # Type-specific extraction
        if document.type == "Microsoft.Compute/virtualMachines":
            return {
                "vmSize": document.properties.get("hardwareProfile", {}).get("vmSize"),
                "osType": document.properties.get("storageProfile", {}).get("osDisk", {}).get("osType"),
                "imageReference": document.properties.get("storageProfile", {}).get("imageReference"),
            }
        elif document.type == "Microsoft.Storage/storageAccounts":
            return {
                "sku": document.properties.get("sku"),
                "kind": document.properties.get("kind"),
                "accessTier": document.properties.get("accessTier"),
            }
        elif document.type == "Microsoft.Network/virtualNetworks":
            return {
                "addressSpace": document.properties.get("addressSpace"),
                "subnets": [s.get("name") for s in document.properties.get("subnets", [])],
            }
        elif document.type == "Microsoft.KeyVault/vaults":
            return {
                "sku": document.properties.get("sku"),
                "enabledForDeployment": document.properties.get("enabledForDeployment"),
                "enableSoftDelete": document.properties.get("enableSoftDelete"),
            }
        else:
            # Generic: extract top-level scalar properties
            return {
                k: v
                for k, v in document.properties.items()
                if isinstance(v, (str, int, float, bool))
            }

    def _chunk_properties(self, document: AzureResourceDocument) -> list[Chunk]:
        """Create additional chunks for large property sets."""
        chunks = []
        properties_json = json.dumps(document.properties, indent=2)

        # Simple chunking: split by size
        for i, start in enumerate(range(0, len(properties_json), self.max_chunk_size)):
            chunk_text = properties_json[start : start + self.max_chunk_size]
            chunks.append(
                Chunk(
                    chunk_id=f"{document.id}:chunk:{i + 1}",
                    doc_id=document.id,
                    doc_type=document.doc_type,
                    text=f"Properties (continued):\n{chunk_text}",
                    heading=f"{document.type}: {document.name} (Properties {i + 1})",
                    chunk_index=i + 1,
                    total_chunks=1,  # Will update
                    resource_type=document.type,
                    resource_name=document.name,
                )
            )

        return chunks


class TerraformResourceChunker:
    """Chunker for Terraform HCL resource documents."""

    def __init__(self, max_chunk_size: int = 2000):
        """Initialize chunker.

        Args:
            max_chunk_size: Maximum characters per chunk
        """
        self.max_chunk_size = max_chunk_size

    def chunk(self, document: TerraformResourceDocument) -> list[Chunk]:
        """Break a Terraform resource document into chunks.

        Args:
            document: Terraform resource document to chunk

        Returns:
            List of chunks
        """
        chunks = []

        # Main chunk: resource definition
        main_text = self._build_main_text(document)
        chunks.append(
            Chunk(
                chunk_id=f"{document.id}:chunk:0",
                doc_id=document.id,
                doc_type=document.doc_type,
                text=main_text,
                heading=f"Terraform: {document.type}.{document.name}",
                chunk_index=0,
                total_chunks=1,
                source_file=document.file_path,
                source_location=f"{document.file_path}:{document.line_number}",
                resource_type=document.type,
                resource_name=document.name,
                properties={
                    "provider": document.provider,
                    "dependencies": document.dependencies,
                },
            )
        )

        # Update total
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _build_main_text(self, document: TerraformResourceDocument) -> str:
        """Build the main text for a Terraform resource chunk."""
        lines = [
            f"Terraform Resource: {document.type}.{document.name}",
            f"File: {document.file_path}",
            f"Line: {document.line_number}",
        ]

        if document.provider:
            lines.append(f"Provider: {document.provider}")

        if document.dependencies:
            lines.append(f"Dependencies: {', '.join(document.dependencies)}")

        # Add source code
        if document.source_code:
            lines.append("\nSource Code:")
            lines.append(document.source_code)

        # Add searchable text if different
        if document.searchable_text and document.searchable_text != document.source_code:
            lines.append("\n" + document.searchable_text)

        return "\n".join(lines)


class TerraformStateChunker:
    """Chunker for Terraform state documents."""

    def __init__(self, max_resources_per_chunk: int = 10):
        """Initialize chunker.

        Args:
            max_resources_per_chunk: Maximum resources per chunk
        """
        self.max_resources_per_chunk = max_resources_per_chunk

    def chunk(self, document: TerraformStateDocument) -> list[Chunk]:
        """Break a Terraform state document into chunks.

        Args:
            document: Terraform state document to chunk

        Returns:
            List of chunks
        """
        chunks = []

        # Overview chunk
        overview_text = self._build_overview_text(document)
        chunks.append(
            Chunk(
                chunk_id=f"{document.id}:chunk:0",
                doc_id=document.id,
                doc_type=document.doc_type,
                text=overview_text,
                heading="Terraform State Overview",
                chunk_index=0,
                total_chunks=1,
                source_file=document.state_file_path,
                properties={
                    "terraform_version": document.terraform_version,
                    "backend": document.backend_type,
                    "workspace": document.workspace,
                    "resource_count": len(document.resources),
                },
            )
        )

        # Chunk resources
        for i in range(0, len(document.resources), self.max_resources_per_chunk):
            resource_batch = document.resources[i : i + self.max_resources_per_chunk]
            chunk_text = self._build_resource_chunk_text(resource_batch)

            chunks.append(
                Chunk(
                    chunk_id=f"{document.id}:chunk:{len(chunks)}",
                    doc_id=document.id,
                    doc_type=document.doc_type,
                    text=chunk_text,
                    heading=f"Terraform State Resources {i + 1}-{i + len(resource_batch)}",
                    chunk_index=len(chunks),
                    total_chunks=1,
                    source_file=document.state_file_path,
                    properties={"resource_count": len(resource_batch)},
                )
            )

        # Update totals
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _build_overview_text(self, document: TerraformStateDocument) -> str:
        """Build overview text for state document."""
        lines = [
            f"Terraform State: {document.workspace}",
            f"Terraform Version: {document.terraform_version}",
            f"Backend: {document.backend_type}",
            f"Serial: {document.serial}",
            f"Total Resources: {len(document.resources)}",
        ]

        if document.outputs:
            lines.append(f"\nOutputs: {', '.join(document.outputs.keys())}")

        return "\n".join(lines)

    def _build_resource_chunk_text(self, resources: list) -> str:
        """Build text for a batch of resources."""
        lines = []
        for resource in resources:
            lines.append(f"\nResource: {resource.address}")
            lines.append(f"  Type: {resource.type}")
            lines.append(f"  Provider: {resource.provider}")
            if resource.sensitive_attributes:
                lines.append(f"  Sensitive Attributes: {', '.join(resource.sensitive_attributes)}")

        return "\n".join(lines)


class TerraformPlanChunker:
    """Chunker for Terraform plan documents.

    Creates a summary chunk plus individual chunks for each planned change.
    """

    def __init__(self):
        """Initialize chunker."""
        pass

    def chunk(self, document: TerraformPlanDocument) -> list[Chunk]:
        """Break a Terraform plan document into chunks.

        Args:
            document: Terraform plan document to chunk

        Returns:
            List of chunks (summary + per-change chunks)
        """
        chunks = []

        # Summary chunk
        summary_text = self._build_summary_text(document)
        chunks.append(
            Chunk(
                chunk_id=f"{document.id}:chunk:0",
                doc_id=document.id,
                doc_type=document.doc_type,
                text=summary_text,
                heading="Terraform Plan Summary",
                chunk_index=0,
                total_chunks=1,
                source_file=f"{document.terraform_dir}/plan",
                properties={
                    "total_add": document.total_add,
                    "total_change": document.total_change,
                    "total_destroy": document.total_destroy,
                    "terraform_version": document.terraform_version,
                },
            )
        )

        # Per-change chunks
        for i, change in enumerate(document.changes):
            change_text = self._build_change_text(change)
            chunks.append(
                Chunk(
                    chunk_id=f"{document.id}:chunk:{i + 1}",
                    doc_id=document.id,
                    doc_type=document.doc_type,
                    text=change_text,
                    heading=f"Plan Change: {change.action} {change.address}",
                    chunk_index=i + 1,
                    total_chunks=1,
                    resource_type=change.resource_type,
                    resource_name=change.address,
                    properties={
                        "action": change.action,
                        "provider": change.provider,
                        "changed_attributes": change.changed_attributes,
                    },
                )
            )

        # Update totals
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _build_summary_text(self, document: TerraformPlanDocument) -> str:
        """Build summary text for plan."""
        lines = [
            f"Terraform Plan: {document.branch}",
            f"Repository: {document.repo_url}",
            f"Commit: {document.commit_sha[:7]}",
            f"Directory: {document.terraform_dir}",
            f"\nPlan: {document.total_add} to add, {document.total_change} to change, {document.total_destroy} to destroy",
        ]

        if document.summary_text:
            lines.append("\n" + document.summary_text)

        return "\n".join(lines)

    def _build_change_text(self, change) -> str:
        """Build text for a single change."""
        lines = [
            f"Action: {change.action.upper()}",
            f"Resource: {change.address}",
            f"Type: {change.resource_type}",
            f"Provider: {change.provider}",
        ]

        if change.changed_attributes:
            lines.append(f"\nChanged Attributes: {', '.join(change.changed_attributes)}")

        if change.action_reason:
            lines.append(f"Reason: {change.action_reason}")

        return "\n".join(lines)


class GitCommitChunker:
    """Chunker for Git commit documents."""

    def __init__(self, max_files_per_chunk: int = 20):
        """Initialize chunker.

        Args:
            max_files_per_chunk: Maximum file changes per chunk
        """
        self.max_files_per_chunk = max_files_per_chunk

    def chunk(self, document: GitCommitDocument) -> list[Chunk]:
        """Break a Git commit document into chunks.

        Args:
            document: Git commit document to chunk

        Returns:
            List of chunks
        """
        chunks = []

        # Main commit chunk
        main_text = self._build_main_text(document)
        chunks.append(
            Chunk(
                chunk_id=f"{document.id}:chunk:0",
                doc_id=document.id,
                doc_type=document.doc_type,
                text=main_text,
                heading=f"Commit {document.short_sha}: {document.message_subject}",
                chunk_index=0,
                total_chunks=1,
                source_location=f"{document.repo_url}/commit/{document.sha}",
                properties={
                    "author": document.author_name,
                    "author_email": document.author_email,
                    "commit_date": document.commit_date.isoformat(),
                    "files_changed": len(document.files_changed),
                    "additions": document.total_additions,
                    "deletions": document.total_deletions,
                    "has_terraform_changes": document.has_terraform_changes,
                },
            )
        )

        # If many file changes, create additional chunks
        if len(document.files_changed) > self.max_files_per_chunk:
            for i in range(0, len(document.files_changed), self.max_files_per_chunk):
                file_batch = document.files_changed[i : i + self.max_files_per_chunk]
                file_text = self._build_file_changes_text(file_batch)

                chunks.append(
                    Chunk(
                        chunk_id=f"{document.id}:chunk:{len(chunks)}",
                        doc_id=document.id,
                        doc_type=document.doc_type,
                        text=file_text,
                        heading=f"Commit {document.short_sha}: Files {i + 1}-{i + len(file_batch)}",
                        chunk_index=len(chunks),
                        total_chunks=1,
                        properties={"file_count": len(file_batch)},
                    )
                )

        # Update totals
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(chunks)

        return chunks

    def _build_main_text(self, document: GitCommitDocument) -> str:
        """Build main text for commit chunk."""
        lines = [
            f"Git Commit: {document.short_sha}",
            f"Author: {document.author_name} <{document.author_email}>",
            f"Date: {document.author_date.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Repository: {document.repo_url}",
            f"Branch: {document.branch}",
            f"\nMessage:\n{document.message}",
            f"\nFiles Changed: {len(document.files_changed)} ({document.total_additions}+ {document.total_deletions}-)",
        ]

        if document.has_terraform_changes:
            lines.append(f"\nTerraform Files: {', '.join(document.terraform_files_changed[:5])}")
            if len(document.terraform_files_changed) > 5:
                lines.append(f"  ... and {len(document.terraform_files_changed) - 5} more")

        # Add searchable text if available
        if document.searchable_text:
            lines.append("\n" + document.searchable_text)

        return "\n".join(lines)

    def _build_file_changes_text(self, files: list) -> str:
        """Build text for a batch of file changes."""
        lines = []
        for file in files:
            lines.append(f"\n{file.change_type.upper()}: {file.path}")
            if file.old_path:
                lines.append(f"  (from {file.old_path})")
            lines.append(f"  +{file.additions} -{file.deletions}")

        return "\n".join(lines)
