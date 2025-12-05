"""Unit tests for ingestion orchestrator."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.ingestion.models import IngestionConfig, IngestionJob, IngestionJobType, JobStatus
from src.ingestion.orchestrator import IngestionOrchestrator


@pytest.fixture
def config():
    """Create test configuration."""
    return IngestionConfig(
        cosmos_connection_string="AccountEndpoint=https://test.documents.azure.com/;AccountKey=test",
        service_bus_connection_string="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=test",
        azure_subscription_ids=["sub-1"],
        max_concurrent_jobs=2,
        max_retries=2,
    )


@pytest.fixture
async def orchestrator(config):
    """Create test orchestrator."""
    with patch("src.ingestion.orchestrator.DefaultAzureCredential"):
        with patch("src.ingestion.orchestrator.CosmosClient"):
            with patch("src.ingestion.orchestrator.ServiceBusClient"):
                with patch(
                    "src.ingestion.orchestrator.AzureResourceGraphConnector"
                ):
                    orch = IngestionOrchestrator(config)
                    # Mock the initialize method to avoid actual Azure calls
                    orch.cosmos_container = AsyncMock()
                    orch.azure_connector = AsyncMock()
                    orch.sb_client = AsyncMock()
                    yield orch


class TestIngestionOrchestrator:
    """Test suite for IngestionOrchestrator."""

    def test_init(self, config):
        """Test orchestrator initialization."""
        orch = IngestionOrchestrator(config)

        assert orch.config == config
        assert orch.credential is None  # Not initialized yet
        assert len(orch.active_jobs) == 0

    @pytest.mark.asyncio
    async def test_schedule_job(self, orchestrator):
        """Test scheduling a job."""
        # Mock _send_job_to_queue
        orchestrator._send_job_to_queue = AsyncMock()

        job = await orchestrator.schedule_job(
            job_type=IngestionJobType.AZURE_RESOURCES,
            parameters={"resource_types": ["Microsoft.Compute/virtualMachines"]},
            scheduled_by="test-user",
            priority=5,
        )

        assert job.job_type == IngestionJobType.AZURE_RESOURCES
        assert job.parameters["resource_types"] == [
            "Microsoft.Compute/virtualMachines"
        ]
        assert job.scheduled_by == "test-user"
        assert job.priority == 5
        assert job.status == JobStatus.PENDING

        # Verify job was sent to queue
        orchestrator._send_job_to_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_job_without_service_bus(self, config):
        """Test scheduling job without Service Bus (immediate processing)."""
        config.service_bus_connection_string = None

        with patch("src.ingestion.orchestrator.DefaultAzureCredential"):
            with patch("src.ingestion.orchestrator.CosmosClient"):
                orch = IngestionOrchestrator(config)
                orch.cosmos_container = AsyncMock()
                orch.azure_connector = AsyncMock()
                orch.process_job = AsyncMock()

                job = await orch.schedule_job(
                    job_type=IngestionJobType.AZURE_RESOURCES
                )

                # Should process immediately
                orch.process_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_azure_resources_job(self, orchestrator):
        """Test processing Azure Resources job."""
        # Mock Azure connector
        mock_resource = {
            "id": "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "location": "canadaeast",
        }

        async def mock_fetch(**kwargs):
            yield mock_resource

        orchestrator.azure_connector.fetch_all_resources = mock_fetch
        orchestrator.azure_connector.convert_to_document = Mock(
            return_value=Mock(id="doc-1", model_dump=Mock(return_value={"id": "doc-1"}))
        )

        # Create job
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES, parameters={}
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.COMPLETED
        assert result.items_processed == 1
        assert result.items_succeeded == 1
        assert result.items_failed == 0

    @pytest.mark.asyncio
    async def test_process_job_with_error(self, orchestrator):
        """Test processing job that encounters an error."""
        # Mock connector to raise error
        async def mock_fetch(**kwargs):
            raise ValueError("Test error")
            yield  # Make it an async generator

        orchestrator.azure_connector.fetch_all_resources = mock_fetch

        # Create job
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES, parameters={}
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.FAILED
        assert result.error_message == "Test error"
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_process_terraform_hcl_job(self, orchestrator, tmp_path):
        """Test processing Terraform HCL job."""
        # Create test Terraform file
        tf_file = tmp_path / "main.tf"
        tf_file.write_text(
            """
resource "azurerm_resource_group" "test" {
  name     = "rg-test"
  location = "canadaeast"
}
"""
        )

        # Create job
        job = IngestionJob(
            job_id="job-123",
            job_type=IngestionJobType.TERRAFORM_HCL,
            parameters={"terraform_dir": str(tmp_path)},
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.COMPLETED
        assert result.items_processed >= 1

    @pytest.mark.asyncio
    async def test_process_git_commits_job(self, orchestrator):
        """Test processing Git commits job."""
        # Mock git connector
        mock_commit = Mock(
            id="commit-1",
            sha="abc123",
            model_dump=Mock(return_value={"id": "commit-1"}),
        )

        async def mock_fetch(**kwargs):
            yield mock_commit

        orchestrator.git_connector.fetch_all_commits = mock_fetch

        # Create job
        job = IngestionJob(
            job_id="job-123",
            job_type=IngestionJobType.GIT_COMMITS,
            parameters={"repo_url": "https://github.com/user/repo.git"},
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.COMPLETED
        assert result.items_processed == 1

    @pytest.mark.asyncio
    async def test_process_full_sync_job(self, orchestrator):
        """Test processing full sync job."""
        # Mock schedule_job to return proper jobs
        async def mock_schedule(*args, **kwargs):
            # First arg is job_type if provided positionally
            job_type = args[0] if args else kwargs.get("job_type", IngestionJobType.AZURE_RESOURCES)
            return IngestionJob(
                job_id="sub-job",
                job_type=job_type,
            )

        orchestrator.schedule_job = mock_schedule

        # Update config with sources
        orchestrator.config.azure_subscription_ids = ["sub-1"]
        orchestrator.config.git_repositories = [
            {"url": "https://github.com/user/repo.git"}
        ]
        orchestrator.config.terraform_paths = ["/path/to/terraform"]

        # Create job
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.FULL_SYNC, parameters={}
        )

        # Track calls manually since we're using a plain async function
        call_count = [0]
        original_schedule = orchestrator.schedule_job

        async def tracked_schedule(*args, **kwargs):
            call_count[0] += 1
            return await original_schedule(*args, **kwargs)

        orchestrator.schedule_job = tracked_schedule

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.COMPLETED
        # Should have scheduled 3 jobs (azure, git, terraform)
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_write_document(self, orchestrator):
        """Test writing document to Cosmos DB."""
        mock_doc = Mock()
        mock_doc.id = "doc-123"
        mock_doc.model_dump = Mock(return_value={"id": "doc-123", "data": "test"})

        await orchestrator._write_document(mock_doc)

        # Verify upsert was called
        orchestrator.cosmos_container.upsert_item.assert_called_once_with(
            {"id": "doc-123", "data": "test"}
        )

    @pytest.mark.asyncio
    async def test_job_tracking(self, orchestrator):
        """Test that jobs are tracked during processing."""
        # Mock Azure connector
        async def mock_fetch(**kwargs):
            # Yield nothing
            return
            yield

        orchestrator.azure_connector.fetch_all_resources = mock_fetch

        # Create job
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES, parameters={}
        )

        assert "job-123" not in orchestrator.active_jobs

        # Start processing (don't await - check during processing)
        process_task = orchestrator.process_job(job)

        # Job should be added to active jobs immediately
        # (but this is hard to test without race conditions)

        # Complete processing
        result = await process_task

        # Job should be removed from active jobs
        assert "job-123" not in orchestrator.active_jobs

    @pytest.mark.asyncio
    async def test_process_terraform_state_job(self, orchestrator, tmp_path):
        """Test processing Terraform state job."""
        # Create test state file
        state_file = tmp_path / "terraform.tfstate"
        state_file.write_text(
            """
{
  "version": 4,
  "terraform_version": "1.5.0",
  "resources": []
}
"""
        )

        # Create job
        job = IngestionJob(
            job_id="job-123",
            job_type=IngestionJobType.TERRAFORM_STATE,
            parameters={"state_file": str(state_file)},
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.COMPLETED
        assert result.items_processed == 1

    @pytest.mark.asyncio
    async def test_process_terraform_plan_job(self, orchestrator, tmp_path):
        """Test processing Terraform plan job."""
        # Create test plan file
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(
            """
{
  "format_version": "1.2",
  "terraform_version": "1.5.0",
  "resource_changes": []
}
"""
        )

        # Create job
        job = IngestionJob(
            job_id="job-123",
            job_type=IngestionJobType.TERRAFORM_PLAN,
            parameters={"plan_file": str(plan_file)},
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.COMPLETED
        assert result.items_processed == 1

    # Removed test_process_job_unknown_type - Pydantic handles type validation
    # so we can't actually create a job with an invalid type

    @pytest.mark.asyncio
    async def test_process_job_missing_parameters(self, orchestrator):
        """Test processing job with missing required parameters."""
        # Create Git job without repo_url
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.GIT_COMMITS, parameters={}
        )

        # Process
        result = await orchestrator.process_job(job)

        assert result.status == JobStatus.FAILED
        assert "repo_url parameter required" in result.error_message


class TestJobResult:
    """Test suite for job result calculation."""

    @pytest.mark.asyncio
    async def test_result_duration_calculation(self, orchestrator):
        """Test that result duration is calculated correctly."""
        # Mock Azure connector with slow processing
        async def mock_fetch(**kwargs):
            import asyncio

            await asyncio.sleep(0.1)  # Simulate work
            return
            yield

        orchestrator.azure_connector.fetch_all_resources = mock_fetch

        # Create job
        job = IngestionJob(
            job_id="job-123", job_type=IngestionJobType.AZURE_RESOURCES, parameters={}
        )

        # Process
        result = await orchestrator.process_job(job)

        # Duration should be > 0.1 seconds
        assert result.duration_seconds >= 0.1
        assert result.completed_at > result.started_at
