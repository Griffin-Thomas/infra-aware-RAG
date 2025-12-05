"""Unit tests for ingestion models."""

from datetime import datetime, timezone

import pytest

from src.ingestion.models import (
    IngestionConfig,
    IngestionJob,
    IngestionJobType,
    JobResult,
    JobStatus,
)


class TestIngestionJob:
    """Test suite for IngestionJob."""

    def test_create_job(self):
        """Test creating a job."""
        job = IngestionJob(
            job_id="job-123",
            job_type=IngestionJobType.AZURE_RESOURCES,
            parameters={"resource_types": ["Microsoft.Compute/virtualMachines"]},
        )

        assert job.job_id == "job-123"
        assert job.job_type == IngestionJobType.AZURE_RESOURCES
        assert job.status == JobStatus.PENDING
        assert job.retry_count == 0
        assert job.items_processed == 0

    def test_mark_started(self):
        """Test marking job as started."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)

        assert job.status == JobStatus.PENDING
        assert job.started_at is None

        job.mark_started()

        assert job.status == JobStatus.RUNNING
        assert job.started_at is not None

    def test_mark_completed(self):
        """Test marking job as completed."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)
        job.mark_started()
        job.mark_completed()

        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None

    def test_mark_failed(self):
        """Test marking job as failed."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)
        job.mark_started()
        job.mark_failed("Something went wrong")

        assert job.status == JobStatus.FAILED
        assert job.error_message == "Something went wrong"
        assert job.completed_at is not None

    def test_is_retryable_true(self):
        """Test job is retryable when under max retries."""
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES, max_retries=3
        )
        job.mark_failed("Error")

        assert job.is_retryable() is True
        assert job.retry_count == 0

    def test_is_retryable_false_max_retries(self):
        """Test job is not retryable when max retries reached."""
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES, max_retries=3
        )
        job.retry_count = 3
        job.mark_failed("Error")

        assert job.is_retryable() is False

    def test_is_retryable_false_not_failed(self):
        """Test job is not retryable when not failed."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)
        job.mark_completed()

        assert job.is_retryable() is False

    def test_increment_retry(self):
        """Test incrementing retry count."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)
        job.mark_failed("Error")

        assert job.retry_count == 0
        assert job.status == JobStatus.FAILED

        job.increment_retry()

        assert job.retry_count == 1
        assert job.status == JobStatus.PENDING

    def test_update_progress(self):
        """Test updating progress."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)

        job.update_progress(10, 100)

        assert job.items_processed == 10
        assert job.items_total == 100

    def test_update_progress_without_total(self):
        """Test updating progress without total."""
        job = IngestionJob(job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES)

        job.update_progress(10)

        assert job.items_processed == 10
        assert job.items_total is None


class TestJobResult:
    """Test suite for JobResult."""

    def test_create_result(self):
        """Test creating a job result."""
        started = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 1, 10, 5, 0, tzinfo=timezone.utc)

        result = JobResult(
            job_id="job-123",
            job_type=IngestionJobType.AZURE_RESOURCES,
            status=JobStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            duration_seconds=300.0,
            items_processed=100,
            items_succeeded=95,
            items_failed=5,
        )

        assert result.job_id == "job-123"
        assert result.status == JobStatus.COMPLETED
        assert result.items_processed == 100
        assert result.items_succeeded == 95
        assert result.items_failed == 5
        assert result.duration_seconds == 300.0

    def test_add_error(self):
        """Test adding errors to result."""
        result = JobResult(
            job_id="job-123",
            job_type=IngestionJobType.AZURE_RESOURCES,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=0.0,
            items_processed=0,
            items_succeeded=0,
            items_failed=0,
        )

        assert len(result.errors) == 0
        assert result.items_failed == 0

        result.add_error("resource-1", "Connection timeout")

        assert len(result.errors) == 1
        assert result.errors[0]["item_id"] == "resource-1"
        assert result.errors[0]["error"] == "Connection timeout"
        assert result.items_failed == 1

    def test_add_multiple_errors(self):
        """Test adding multiple errors."""
        result = JobResult(
            job_id="job-123",
            job_type=IngestionJobType.AZURE_RESOURCES,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_seconds=0.0,
            items_processed=0,
            items_succeeded=0,
            items_failed=0,
        )

        result.add_error("resource-1", "Error 1")
        result.add_error("resource-2", "Error 2")
        result.add_error("resource-3", "Error 3")

        assert len(result.errors) == 3
        assert result.items_failed == 3


class TestIngestionConfig:
    """Test suite for IngestionConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = IngestionConfig()

        assert config.service_bus_queue_name == "ingestion-jobs"
        assert config.cosmos_database_name == "infra-rag"
        assert config.cosmos_container_name == "documents"
        assert config.max_concurrent_jobs == 5
        assert config.max_retries == 3
        assert config.batch_size == 100

    def test_custom_config(self):
        """Test custom configuration."""
        config = IngestionConfig(
            service_bus_connection_string="Endpoint=sb://test.servicebus.windows.net/",
            cosmos_connection_string="AccountEndpoint=https://test.documents.azure.com/",
            azure_subscription_ids=["sub-1", "sub-2"],
            max_concurrent_jobs=10,
        )

        assert config.service_bus_connection_string.startswith("Endpoint=")
        assert config.cosmos_connection_string.startswith("AccountEndpoint=")
        assert len(config.azure_subscription_ids) == 2
        assert config.max_concurrent_jobs == 10

    def test_config_with_git_repos(self):
        """Test configuration with Git repositories."""
        config = IngestionConfig(
            git_repositories=[
                {"url": "https://github.com/user/repo1.git", "branch": "main"},
                {"url": "https://github.com/user/repo2.git", "branch": "develop"},
            ]
        )

        assert len(config.git_repositories) == 2
        assert config.git_repositories[0]["branch"] == "main"
        assert config.git_repositories[1]["branch"] == "develop"

    def test_config_with_terraform_paths(self):
        """Test configuration with Terraform paths."""
        config = IngestionConfig(
            terraform_paths=["/path/to/terraform1", "/path/to/terraform2"]
        )

        assert len(config.terraform_paths) == 2


class TestIngestionJobType:
    """Test suite for IngestionJobType enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert IngestionJobType.AZURE_RESOURCES.value == "azure_resources"
        assert IngestionJobType.TERRAFORM_HCL.value == "terraform_hcl"
        assert IngestionJobType.TERRAFORM_STATE.value == "terraform_state"
        assert IngestionJobType.TERRAFORM_PLAN.value == "terraform_plan"
        assert IngestionJobType.GIT_COMMITS.value == "git_commits"
        assert IngestionJobType.FULL_SYNC.value == "full_sync"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        job_type = IngestionJobType("azure_resources")
        assert job_type == IngestionJobType.AZURE_RESOURCES


class TestJobStatus:
    """Test suite for JobStatus enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"
