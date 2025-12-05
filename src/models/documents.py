"""Data models for ingested documents."""

from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class AzureResourceDocument(BaseModel):
    """Document stored for each Azure resource."""

    # Identity
    id: str = Field(..., description="Azure Resource ID")
    doc_type: str = "azure_resource"

    # Core properties
    name: str
    type: str  # e.g., "Microsoft.Compute/virtualMachines"
    resource_group: str
    subscription_id: str
    subscription_name: str
    location: str

    # Metadata
    tags: dict[str, str] = Field(default_factory=dict)
    sku: dict[str, Any] | None = None
    kind: str | None = None
    managed_by: str | None = None

    # Full properties (for detailed queries)
    properties: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_time: datetime | None = None
    changed_time: datetime | None = None
    ingested_at: datetime = Field(default_factory=utc_now)

    # Relationships (populated during enrichment)
    terraform_address: str | None = None
    parent_resource_id: str | None = None
    child_resource_ids: list[str] = Field(default_factory=list)

    # Searchable text (generated for embedding)
    searchable_text: str = ""

    def generate_searchable_text(self) -> str:
        """Generate text for embedding."""
        parts = [
            f"Azure Resource: {self.name}",
            f"Type: {self.type}",
            f"Resource Group: {self.resource_group}",
            f"Location: {self.location}",
        ]
        if self.tags:
            parts.append(f"Tags: {', '.join(f'{k}={v}' for k, v in self.tags.items())}")
        if self.sku:
            parts.append(f"SKU: {self.sku}")
        return "\n".join(parts)


class TerraformResourceDocument(BaseModel):
    """Document stored for each Terraform resource definition."""

    # Identity
    id: str = Field(..., description="Unique ID: {repo}:{path}:{address}")
    doc_type: str = "terraform_resource"

    # Resource identity
    address: str  # e.g., "module.network.azurerm_virtual_network.main"
    type: str  # e.g., "azurerm_virtual_network"
    name: str  # e.g., "main"
    module_path: str | None = None  # e.g., "module.network"

    # Source location
    repo_url: str
    branch: str
    file_path: str
    line_number: int
    source_code: str  # The HCL block

    # Terraform metadata
    provider: str  # e.g., "azurerm"
    provider_version: str | None = None

    # Configuration
    attributes: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)  # Explicit depends_on
    implicit_dependencies: list[str] = Field(default_factory=list)  # Reference-based

    # Relationships
    azure_resource_id: str | None = None  # Linked Azure resource

    # Timestamps
    last_commit_sha: str
    last_commit_date: datetime
    ingested_at: datetime = Field(default_factory=utc_now)

    # Searchable text
    searchable_text: str = ""

    def generate_searchable_text(self) -> str:
        """Generate text for embedding."""
        return f"""Terraform Resource: {self.address}
Type: {self.type}
Provider: {self.provider}
File: {self.file_path}

Source Code:
{self.source_code}"""


class TerraformStateResource(BaseModel):
    """A resource from Terraform state file."""

    address: str
    type: str
    name: str
    provider: str
    mode: str  # "managed" or "data"

    # The actual resource attributes from state
    attributes: dict[str, Any]

    # Sensitive attributes (redacted)
    sensitive_attributes: list[str] = Field(default_factory=list)

    # Dependencies
    dependencies: list[str] = Field(default_factory=list)


class TerraformStateDocument(BaseModel):
    """Document for a Terraform state file."""

    id: str  # Unique ID based on backend + workspace
    doc_type: str = "terraform_state"

    # State identity
    state_file_path: str | None = None  # For local state
    backend_type: str  # "local", "azurerm", "s3", etc.
    workspace: str = "default"

    # State metadata
    terraform_version: str
    serial: int
    lineage: str

    # Resources in this state
    resources: list[TerraformStateResource]

    # Outputs (non-sensitive only)
    outputs: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    state_timestamp: datetime | None = None
    ingested_at: datetime = Field(default_factory=utc_now)


class PlannedChange(BaseModel):
    """A single resource change from a Terraform plan."""

    address: str
    action: str  # "create", "update", "delete", "replace", "read", "no-op"

    # Resource type info
    resource_type: str
    provider: str

    # Change details
    before: dict[str, Any] | None = None  # Current state
    after: dict[str, Any] | None = None  # Planned state
    after_unknown: dict[str, Any] | None = None  # Values known after apply

    # Attribute-level changes
    changed_attributes: list[str] = Field(default_factory=list)

    # Why this action?
    action_reason: str | None = None  # e.g., "replace_because_cannot_update"


class TerraformPlanDocument(BaseModel):
    """Document for a Terraform plan."""

    id: str  # Unique plan ID
    doc_type: str = "terraform_plan"

    # Source
    repo_url: str
    branch: str
    commit_sha: str
    terraform_dir: str  # Directory where plan was run

    # Plan metadata
    terraform_version: str
    plan_timestamp: datetime

    # Changes summary
    total_add: int = 0
    total_change: int = 0
    total_destroy: int = 0

    # All changes
    changes: list[PlannedChange]

    # Human-readable summary
    summary_text: str = ""

    # Timestamps
    ingested_at: datetime = Field(default_factory=utc_now)


class GitFileChange(BaseModel):
    """A single file change in a commit."""

    path: str
    change_type: str  # "add", "modify", "delete", "rename"
    old_path: str | None = None  # For renames
    additions: int = 0
    deletions: int = 0


class GitCommitDocument(BaseModel):
    """Document for a Git commit."""

    id: str  # "{repo_url}:{sha}"
    doc_type: str = "git_commit"

    # Commit identity
    sha: str
    short_sha: str

    # Repository
    repo_url: str
    branch: str

    # Commit metadata
    message: str
    message_subject: str  # First line
    message_body: str  # Rest of message

    # Author info
    author_name: str
    author_email: str
    author_date: datetime

    # Committer info (can differ from author)
    committer_name: str
    committer_email: str
    commit_date: datetime

    # Changes
    files_changed: list[GitFileChange]
    total_additions: int = 0
    total_deletions: int = 0

    # Terraform-specific
    terraform_files_changed: list[str] = Field(default_factory=list)
    has_terraform_changes: bool = False

    # Timestamps
    ingested_at: datetime = Field(default_factory=utc_now)

    # Searchable text
    searchable_text: str = ""

    def generate_searchable_text(self) -> str:
        """Generate text for embedding."""
        files_str = "\n".join(f"  - {f.path} ({f.change_type})" for f in self.files_changed)
        return f"""Git Commit: {self.short_sha}
Author: {self.author_name} <{self.author_email}>
Date: {self.author_date.isoformat()}

{self.message}

Files Changed:
{files_str}"""
