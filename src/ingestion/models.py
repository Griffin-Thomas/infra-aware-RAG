"""Data models for ingestion orchestration."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.models.documents import utc_now


class IngestionJobType(str, Enum):
    """Types of ingestion jobs."""

    AZURE_RESOURCES = "azure_resources"
    TERRAFORM_HCL = "terraform_hcl"
    TERRAFORM_STATE = "terraform_state"
    TERRAFORM_PLAN = "terraform_plan"
    GIT_COMMITS = "git_commits"
    FULL_SYNC = "full_sync"  # Run all ingestion types


class JobStatus(str, Enum):
    """Status of an ingestion job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionJob(BaseModel):
    """An ingestion job to be processed."""

    # Identity
    job_id: str
    job_type: IngestionJobType

    # Timing
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Status
    status: JobStatus = JobStatus.PENDING
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 3

    # Job-specific parameters
    parameters: dict[str, Any] = Field(default_factory=dict)

    # Progress tracking
    progress: dict[str, Any] = Field(default_factory=dict)
    items_processed: int = 0
    items_total: int | None = None

    # Metadata
    scheduled_by: str | None = None  # User or system that scheduled the job
    priority: int = 0  # Higher priority jobs processed first

    def is_retryable(self) -> bool:
        """Check if job can be retried."""
        return self.retry_count < self.max_retries and self.status == JobStatus.FAILED

    def mark_started(self) -> None:
        """Mark job as started."""
        self.status = JobStatus.RUNNING
        self.started_at = utc_now()

    def mark_completed(self) -> None:
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.completed_at = utc_now()

    def mark_failed(self, error_message: str) -> None:
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.completed_at = utc_now()

    def increment_retry(self) -> None:
        """Increment retry count."""
        self.retry_count += 1
        self.status = JobStatus.PENDING

    def update_progress(self, items_processed: int, items_total: int | None = None) -> None:
        """Update progress counters."""
        self.items_processed = items_processed
        if items_total is not None:
            self.items_total = items_total


class IngestionConfig(BaseModel):
    """Configuration for ingestion orchestration."""

    # Azure Service Bus
    service_bus_connection_string: str | None = None
    service_bus_queue_name: str = "ingestion-jobs"

    # Cosmos DB
    cosmos_connection_string: str | None = None
    cosmos_endpoint: str | None = None  # Alternative to connection_string (uses DefaultAzureCredential)
    cosmos_database_name: str = "infra-rag"
    cosmos_container_name: str = "documents"

    # Azure Resource Graph
    azure_subscription_ids: list[str] = Field(default_factory=list)
    azure_resource_types: list[str] | None = None  # None = all types

    # Git repositories
    git_repositories: list[dict[str, Any]] = Field(default_factory=list)
    # Each repo: {"url": "...", "branch": "main", "auth_token": "..."}

    # Terraform paths
    terraform_paths: list[str] = Field(default_factory=list)

    # Job settings
    max_concurrent_jobs: int = 5
    job_timeout_seconds: int = 3600  # 1 hour
    poll_interval_seconds: int = 5

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: int = 60

    # Batch settings
    batch_size: int = 100  # Documents per batch to Cosmos DB


class JobResult(BaseModel):
    """Result of a completed ingestion job."""

    job_id: str
    job_type: IngestionJobType
    status: JobStatus

    # Timing
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # Metrics
    items_processed: int
    items_succeeded: int
    items_failed: int

    # Documents
    document_ids: list[str] = Field(default_factory=list)

    # Errors
    error_message: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)

    def add_error(self, item_id: str, error: str) -> None:
        """Add an item-level error."""
        self.errors.append({"item_id": item_id, "error": error})
        self.items_failed += 1
