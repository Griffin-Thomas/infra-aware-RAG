"""Ingestion orchestration for coordinating data collection from all sources."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver, ServiceBusSender

from src.ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector
from src.ingestion.connectors.git_connector import GitConnector
from src.ingestion.connectors.terraform_hcl import TerraformHCLConnector
from src.ingestion.connectors.terraform_plan import TerraformPlanConnector
from src.ingestion.connectors.terraform_state import TerraformStateConnector
from src.ingestion.models import (
    IngestionConfig,
    IngestionJob,
    IngestionJobType,
    JobResult,
    JobStatus,
)
from src.models.documents import (
    AzureResourceDocument,
    GitCommitDocument,
    TerraformPlanDocument,
    TerraformResourceDocument,
    TerraformStateDocument,
)

logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """Orchestrates data ingestion from all sources.

    Coordinates connectors, schedules jobs via Service Bus, and writes
    documents to Cosmos DB.
    """

    def __init__(self, config: IngestionConfig):
        """Initialize orchestrator with configuration.

        Args:
            config: Ingestion configuration
        """
        self.config = config

        # Azure clients (initialized in async context)
        self.credential: DefaultAzureCredential | None = None
        self.cosmos_client: CosmosClient | None = None
        self.sb_client: ServiceBusClient | None = None
        self.cosmos_container = None

        # Connectors
        self.azure_connector: AzureResourceGraphConnector | None = None
        self.git_connector = GitConnector(track_terraform_only=True)
        self.hcl_connector: TerraformHCLConnector | None = None
        self.state_connector = TerraformStateConnector()
        self.plan_connector = TerraformPlanConnector()

        # Job tracking
        self.active_jobs: dict[str, IngestionJob] = {}

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self) -> None:
        """Initialize Azure clients and connectors."""
        logger.info("Initializing ingestion orchestrator")

        # Initialize credential
        self.credential = DefaultAzureCredential()

        # Initialize Cosmos DB client
        if self.config.cosmos_connection_string:
            self.cosmos_client = CosmosClient(self.config.cosmos_connection_string)
        elif self.config.cosmos_endpoint:
            # Use credential-based auth with DefaultAzureCredential
            self.cosmos_client = CosmosClient(
                url=self.config.cosmos_endpoint,
                credential=self.credential,
            )
        else:
            raise ValueError("Either cosmos_connection_string or cosmos_endpoint is required")

        # Get database and container
        database = self.cosmos_client.get_database_client(
            self.config.cosmos_database_name
        )
        self.cosmos_container = database.get_container_client(
            self.config.cosmos_container_name
        )

        # Initialize Service Bus client
        if self.config.service_bus_connection_string:
            self.sb_client = ServiceBusClient.from_connection_string(
                self.config.service_bus_connection_string
            )

        # Initialize Azure Resource Graph connector
        self.azure_connector = AzureResourceGraphConnector(
            credential=self.credential,
            subscription_ids=self.config.azure_subscription_ids,
        )
        await self.azure_connector.__aenter__()

        logger.info("Orchestrator initialized successfully")

    async def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up orchestrator")

        # Close Azure Resource Graph connector
        if self.azure_connector:
            await self.azure_connector.__aexit__(None, None, None)

        # Close Cosmos client
        if self.cosmos_client:
            await self.cosmos_client.close()

        # Close Service Bus client
        if self.sb_client:
            await self.sb_client.close()

        # Close credential
        if self.credential:
            await self.credential.close()

        logger.info("Orchestrator cleanup complete")

    # -------------------------------------------------------------------------
    # Job Scheduling
    # -------------------------------------------------------------------------

    async def schedule_job(
        self,
        job_type: IngestionJobType,
        parameters: dict[str, Any] | None = None,
        scheduled_by: str | None = None,
        priority: int = 0,
    ) -> IngestionJob:
        """Schedule an ingestion job.

        Args:
            job_type: Type of job to schedule
            parameters: Job-specific parameters
            scheduled_by: User or system scheduling the job
            priority: Job priority (higher = more urgent)

        Returns:
            Created job
        """
        # Create job
        job = IngestionJob(
            job_id=str(uuid.uuid4()),
            job_type=job_type,
            parameters=parameters or {},
            scheduled_by=scheduled_by,
            priority=priority,
            max_retries=self.config.max_retries,
        )

        logger.info(f"Scheduling job {job.job_id} (type={job_type})")

        # Send to Service Bus if available
        if self.sb_client:
            await self._send_job_to_queue(job)
        else:
            # Process immediately if no Service Bus
            await self.process_job(job)

        return job

    async def _send_job_to_queue(self, job: IngestionJob) -> None:
        """Send job to Service Bus queue.

        Args:
            job: Job to send
        """
        sender: ServiceBusSender = self.sb_client.get_queue_sender(
            self.config.service_bus_queue_name
        )

        async with sender:
            message = {
                "job_id": job.job_id,
                "job_type": job.job_type.value,
                "parameters": job.parameters,
            }
            await sender.send_messages(message)

        logger.info(f"Job {job.job_id} sent to queue")

    # -------------------------------------------------------------------------
    # Job Processing
    # -------------------------------------------------------------------------

    async def process_job(self, job: IngestionJob) -> JobResult:
        """Process an ingestion job.

        Args:
            job: Job to process

        Returns:
            Job result
        """
        logger.info(f"Processing job {job.job_id} (type={job.job_type})")

        # Mark as started
        job.mark_started()
        self.active_jobs[job.job_id] = job

        # Create result
        result = JobResult(
            job_id=job.job_id,
            job_type=job.job_type,
            status=JobStatus.RUNNING,
            started_at=job.started_at,
            completed_at=datetime.now(UTC),
            duration_seconds=0.0,
            items_processed=0,
            items_succeeded=0,
            items_failed=0,
        )

        try:
            # Route to appropriate handler
            if job.job_type == IngestionJobType.AZURE_RESOURCES:
                await self._process_azure_resources(job, result)
            elif job.job_type == IngestionJobType.TERRAFORM_HCL:
                await self._process_terraform_hcl(job, result)
            elif job.job_type == IngestionJobType.TERRAFORM_STATE:
                await self._process_terraform_state(job, result)
            elif job.job_type == IngestionJobType.TERRAFORM_PLAN:
                await self._process_terraform_plan(job, result)
            elif job.job_type == IngestionJobType.GIT_COMMITS:
                await self._process_git_commits(job, result)
            elif job.job_type == IngestionJobType.FULL_SYNC:
                await self._process_full_sync(job, result)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")

            # Mark as completed
            job.mark_completed()
            result.status = JobStatus.COMPLETED

        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {e}", exc_info=True)
            job.mark_failed(str(e))
            result.status = JobStatus.FAILED
            result.error_message = str(e)

        finally:
            # Calculate duration
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()

            # Remove from active jobs
            self.active_jobs.pop(job.job_id, None)

        logger.info(
            f"Job {job.job_id} completed: {result.items_succeeded} succeeded, "
            f"{result.items_failed} failed"
        )

        return result

    async def _process_azure_resources(
        self, job: IngestionJob, result: JobResult
    ) -> None:
        """Process Azure Resource Graph ingestion job."""
        if not self.azure_connector:
            raise RuntimeError("Azure connector not initialized")

        # Get parameters
        resource_types = job.parameters.get("resource_types")
        query = job.parameters.get("query")

        # Fetch resources
        async for resource_dict in self.azure_connector.fetch_all_resources(
            query=query, resource_types=resource_types
        ):
            try:
                # Convert to document
                doc = self.azure_connector.convert_to_document(resource_dict)

                # Write to Cosmos DB
                await self._write_document(doc)

                result.items_succeeded += 1
                result.document_ids.append(doc.id)

            except Exception as e:
                logger.error(f"Failed to process resource: {e}")
                result.add_error(resource_dict.get("id", "unknown"), str(e))

            result.items_processed += 1
            job.update_progress(result.items_processed)

    async def _process_terraform_hcl(
        self, job: IngestionJob, result: JobResult
    ) -> None:
        """Process Terraform HCL ingestion job."""
        terraform_dir = job.parameters.get("terraform_dir")
        if not terraform_dir:
            raise ValueError("terraform_dir parameter required")

        # Initialize connector
        connector = TerraformHCLConnector(Path(terraform_dir))

        # Parse all files
        for parsed_file in connector.parse_all():
            try:
                # Convert resources to documents
                for resource in parsed_file.resources:
                    doc = connector.convert_to_document(
                        resource=resource,
                        file_path=parsed_file.path,
                        repo_url=job.parameters.get("repo_url", ""),
                        branch=job.parameters.get("branch", "main"),
                        commit_sha=job.parameters.get("commit_sha", ""),
                    )

                    # Write to Cosmos DB
                    await self._write_document(doc)

                    result.items_succeeded += 1
                    result.document_ids.append(doc.id)

            except Exception as e:
                logger.error(f"Failed to process Terraform file: {e}")
                result.add_error(parsed_file.path, str(e))

            result.items_processed += 1
            job.update_progress(result.items_processed)

    async def _process_terraform_state(
        self, job: IngestionJob, result: JobResult
    ) -> None:
        """Process Terraform state ingestion job."""
        state_file = job.parameters.get("state_file")
        if not state_file:
            raise ValueError("state_file parameter required")

        try:
            # Parse state file
            processed = self.state_connector.parse_state_file(Path(state_file))

            # Convert to document
            doc = self.state_connector.convert_to_document(
                processed_state=processed,
                state_id=job.parameters.get("state_id", str(uuid.uuid4())),
                state_file_path=state_file,
                backend_type=job.parameters.get("backend_type", "local"),
                workspace=job.parameters.get("workspace", "default"),
            )

            # Write to Cosmos DB
            await self._write_document(doc)

            result.items_succeeded += 1
            result.document_ids.append(doc.id)

        except Exception as e:
            logger.error(f"Failed to process state file: {e}")
            result.add_error(state_file, str(e))

        result.items_processed += 1

    async def _process_terraform_plan(
        self, job: IngestionJob, result: JobResult
    ) -> None:
        """Process Terraform plan ingestion job."""
        plan_file = job.parameters.get("plan_file")
        if not plan_file:
            raise ValueError("plan_file parameter required")

        try:
            # Parse plan file
            processed = self.plan_connector.parse_plan_file(Path(plan_file))

            # Convert to document
            doc = self.plan_connector.convert_to_document(
                processed_plan=processed,
                plan_id=job.parameters.get("plan_id", str(uuid.uuid4())),
                repo_url=job.parameters.get("repo_url", ""),
                branch=job.parameters.get("branch", "main"),
                commit_sha=job.parameters.get("commit_sha", ""),
                terraform_dir=job.parameters.get("terraform_dir", ""),
                plan_timestamp=datetime.now(UTC),
            )

            # Write to Cosmos DB
            await self._write_document(doc)

            result.items_succeeded += 1
            result.document_ids.append(doc.id)

        except Exception as e:
            logger.error(f"Failed to process plan file: {e}")
            result.add_error(plan_file, str(e))

        result.items_processed += 1

    async def _process_git_commits(
        self, job: IngestionJob, result: JobResult
    ) -> None:
        """Process Git commit ingestion job."""
        repo_url = job.parameters.get("repo_url")
        if not repo_url:
            raise ValueError("repo_url parameter required")

        # Get parameters
        branch = job.parameters.get("branch")
        since = job.parameters.get("since")
        until = job.parameters.get("until")
        auth_token = job.parameters.get("auth_token")

        # Fetch commits
        async for doc in self.git_connector.fetch_all_commits(
            repo_url=repo_url,
            branch=branch,
            since=since,
            until=until,
            auth_token=auth_token,
        ):
            try:
                # Write to Cosmos DB
                await self._write_document(doc)

                result.items_succeeded += 1
                result.document_ids.append(doc.id)

            except Exception as e:
                logger.error(f"Failed to process commit: {e}")
                result.add_error(doc.sha, str(e))

            result.items_processed += 1
            job.update_progress(result.items_processed)

    async def _process_full_sync(self, job: IngestionJob, result: JobResult) -> None:
        """Process full sync job (all sources)."""
        # Schedule individual jobs for each source
        jobs = []

        # Azure resources
        if self.config.azure_subscription_ids:
            azure_job = await self.schedule_job(
                IngestionJobType.AZURE_RESOURCES,
                parameters={"resource_types": self.config.azure_resource_types},
                scheduled_by=job.scheduled_by,
            )
            jobs.append(azure_job)

        # Git repositories
        for repo_config in self.config.git_repositories:
            git_job = await self.schedule_job(
                IngestionJobType.GIT_COMMITS,
                parameters=repo_config,
                scheduled_by=job.scheduled_by,
            )
            jobs.append(git_job)

        # Terraform paths
        for tf_path in self.config.terraform_paths:
            hcl_job = await self.schedule_job(
                IngestionJobType.TERRAFORM_HCL,
                parameters={"terraform_dir": tf_path},
                scheduled_by=job.scheduled_by,
            )
            jobs.append(hcl_job)

        logger.info(f"Full sync scheduled {len(jobs)} jobs")
        result.items_processed = len(jobs)
        result.items_succeeded = len(jobs)

    # -------------------------------------------------------------------------
    # Document Storage
    # -------------------------------------------------------------------------

    async def _write_document(
        self,
        document: (
            AzureResourceDocument
            | TerraformResourceDocument
            | TerraformStateDocument
            | TerraformPlanDocument
            | GitCommitDocument
        ),
    ) -> None:
        """Write a document to Cosmos DB.

        Args:
            document: Document to write
        """
        if not self.cosmos_container:
            raise RuntimeError("Cosmos container not initialized")

        # Convert to dict
        doc_dict = document.model_dump(mode="json")

        # Upsert to Cosmos DB
        await self.cosmos_container.upsert_item(doc_dict)

        logger.debug(f"Wrote document {document.id} to Cosmos DB")

    # -------------------------------------------------------------------------
    # Job Workers
    # -------------------------------------------------------------------------

    async def start_worker(self) -> None:
        """Start a job worker that processes jobs from the queue.

        Runs indefinitely until cancelled.
        """
        if not self.sb_client:
            raise RuntimeError("Service Bus client not initialized")

        logger.info("Starting job worker")

        receiver: ServiceBusReceiver = self.sb_client.get_queue_receiver(
            self.config.service_bus_queue_name
        )

        async with receiver:
            while True:
                try:
                    # Receive messages
                    messages = await receiver.receive_messages(
                        max_message_count=1,
                        max_wait_time=self.config.poll_interval_seconds,
                    )

                    for message in messages:
                        try:
                            # Parse job from message
                            job_data = message.body
                            job = IngestionJob(
                                job_id=job_data["job_id"],
                                job_type=IngestionJobType(job_data["job_type"]),
                                parameters=job_data.get("parameters", {}),
                            )

                            # Process job
                            await self.process_job(job)

                            # Complete message
                            await receiver.complete_message(message)

                        except Exception as e:
                            logger.error(f"Failed to process message: {e}")
                            # Dead-letter the message
                            await receiver.dead_letter_message(
                                message, reason=str(e)
                            )

                except asyncio.CancelledError:
                    logger.info("Worker cancelled")
                    break
                except Exception as e:
                    logger.error(f"Worker error: {e}", exc_info=True)
                    await asyncio.sleep(self.config.retry_delay_seconds)

        logger.info("Job worker stopped")
