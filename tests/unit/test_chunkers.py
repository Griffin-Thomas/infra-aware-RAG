"""Unit tests for chunkers."""

from datetime import datetime, timezone

import pytest

from src.indexing.chunkers import (
    AzureResourceChunker,
    GitCommitChunker,
    TerraformPlanChunker,
    TerraformResourceChunker,
    TerraformStateChunker,
)
from src.models.documents import (
    AzureResourceDocument,
    GitCommitDocument,
    GitFileChange,
    PlannedChange,
    TerraformPlanDocument,
    TerraformResourceDocument,
    TerraformStateDocument,
    TerraformStateResource,
)


class TestAzureResourceChunker:
    """Test suite for AzureResourceChunker."""

    def test_chunk_simple_resource(self):
        """Test chunking a simple Azure resource."""
        doc = AzureResourceDocument(
            id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            type="Microsoft.Compute/virtualMachines",
            name="vm-1",
            resource_group="rg-1",
            location="canadaeast",
            subscription_id="sub-1",
            subscription_name="Production",
            tags={"Environment": "prod", "Owner": "team-a"},
            properties={"hardwareProfile": {"vmSize": "Standard_D2s_v3"}},
        )

        chunker = AzureResourceChunker()
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        assert chunks[0].doc_id == doc.id
        assert chunks[0].doc_type == "azure_resource"
        assert chunks[0].resource_type == "Microsoft.Compute/virtualMachines"
        assert chunks[0].resource_name == "vm-1"
        assert chunks[0].tags == {"Environment": "prod", "Owner": "team-a"}
        assert "Standard_D2s_v3" in chunks[0].text

    def test_extract_vm_properties(self):
        """Test extracting VM-specific properties."""
        doc = AzureResourceDocument(
            id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            type="Microsoft.Compute/virtualMachines",
            name="vm-1",
            resource_group="rg-1",
            location="canadaeast",
            subscription_id="sub-1",
            subscription_name="Production",
            properties={
                "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "storageProfile": {
                    "osDisk": {"osType": "Linux"},
                    "imageReference": {"publisher": "Canonical", "offer": "UbuntuServer"},
                },
            },
        )

        chunker = AzureResourceChunker()
        props = chunker._extract_key_properties(doc)

        assert props["vmSize"] == "Standard_D2s_v3"
        assert props["osType"] == "Linux"
        assert props["imageReference"]["publisher"] == "Canonical"

    def test_extract_storage_properties(self):
        """Test extracting storage account properties."""
        doc = AzureResourceDocument(
            id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Storage/storageAccounts/sa1",
            type="Microsoft.Storage/storageAccounts",
            name="sa1",
            resource_group="rg-1",
            location="canadaeast",
            subscription_id="sub-1",
            subscription_name="Production",
            properties={
                "sku": {"name": "Standard_LRS"},
                "kind": "StorageV2",
                "accessTier": "Hot",
            },
        )

        chunker = AzureResourceChunker()
        props = chunker._extract_key_properties(doc)

        assert props["sku"] == {"name": "Standard_LRS"}
        assert props["kind"] == "StorageV2"
        assert props["accessTier"] == "Hot"

    def test_chunk_with_large_properties(self):
        """Test chunking resource with large properties."""
        # Create a large properties dict
        large_props = {f"property_{i}": f"value_{i}" * 100 for i in range(100)}

        doc = AzureResourceDocument(
            id="/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            type="Microsoft.Compute/virtualMachines",
            name="vm-1",
            resource_group="rg-1",
            location="canadaeast",
            subscription_id="sub-1",
            subscription_name="Production",
            properties=large_props,
        )

        chunker = AzureResourceChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        # Should create multiple chunks
        assert len(chunks) > 1
        assert all(chunk.doc_id == doc.id for chunk in chunks)
        assert all(chunk.total_chunks == len(chunks) for chunk in chunks)


class TestTerraformResourceChunker:
    """Test suite for TerraformResourceChunker."""

    def test_chunk_terraform_resource(self):
        """Test chunking a Terraform resource."""
        doc = TerraformResourceDocument(
            id="terraform:repo:main:abc123:azurerm_resource_group.main",
            address="azurerm_resource_group.main",
            type="azurerm_resource_group",
            name="main",
            file_path="main.tf",
            line_number=1,
            repo_url="https://github.com/user/repo.git",
            branch="main",
            last_commit_sha="abc123",
            last_commit_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            provider="azurerm",
            source_code='resource "azurerm_resource_group" "main" {\n  name = "rg-test"\n  location = "canadaeast"\n}',
            dependencies=["azurerm_virtual_network.main"],
        )

        chunker = TerraformResourceChunker()
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        assert chunks[0].doc_id == doc.id
        assert chunks[0].resource_type == "azurerm_resource_group"
        assert chunks[0].resource_name == "main"
        assert chunks[0].source_file == "main.tf"
        assert "canadaeast" in chunks[0].text
        assert chunks[0].properties["dependencies"] == ["azurerm_virtual_network.main"]


class TestTerraformStateChunker:
    """Test suite for TerraformStateChunker."""

    def test_chunk_state_overview(self):
        """Test chunking Terraform state overview."""
        resources = [
            TerraformStateResource(
                address="azurerm_resource_group.main",
                type="azurerm_resource_group",
                name="main",
                provider="azurerm",
                mode="managed",
                attributes={"name": "rg-test", "location": "canadaeast"},
            )
        ]

        doc = TerraformStateDocument(
            id="terraform:state:workspace:default",
            state_file_path="/terraform/terraform.tfstate",
            backend_type="local",
            workspace="default",
            terraform_version="1.5.0",
            serial=1,
            lineage="abc-123",
            resources=resources,
            outputs={"resource_group_name": {"value": "rg-test", "sensitive": False}},
        )

        chunker = TerraformStateChunker()
        chunks = chunker.chunk(doc)

        # Should have overview + resource chunks
        assert len(chunks) >= 1
        assert chunks[0].heading == "Terraform State Overview"
        assert "Terraform Version: 1.5.0" in chunks[0].text
        assert chunks[0].properties["resource_count"] == 1

    def test_chunk_state_with_many_resources(self):
        """Test chunking state with many resources."""
        resources = [
            TerraformStateResource(
                address=f"azurerm_resource.resource_{i}",
                type="azurerm_resource",
                name=f"resource_{i}",
                provider="azurerm",
                mode="managed",
                attributes={},
            )
            for i in range(25)
        ]

        doc = TerraformStateDocument(
            id="terraform:state:workspace:default",
            state_file_path="/terraform/terraform.tfstate",
            backend_type="local",
            workspace="default",
            terraform_version="1.5.0",
            serial=1,
            lineage="abc-123",
            resources=resources,
        )

        chunker = TerraformStateChunker(max_resources_per_chunk=10)
        chunks = chunker.chunk(doc)

        # Should have overview + 3 resource chunks (25 resources / 10 per chunk)
        assert len(chunks) == 4
        assert chunks[0].heading == "Terraform State Overview"


class TestTerraformPlanChunker:
    """Test suite for TerraformPlanChunker."""

    def test_chunk_plan_summary(self):
        """Test chunking Terraform plan summary."""
        changes = [
            PlannedChange(
                address="azurerm_resource_group.main",
                action="create",
                resource_type="azurerm_resource_group",
                provider="azurerm",
                changed_attributes=["name", "location"],
            ),
            PlannedChange(
                address="azurerm_virtual_network.main",
                action="update",
                resource_type="azurerm_virtual_network",
                provider="azurerm",
                changed_attributes=["address_space"],
            ),
        ]

        doc = TerraformPlanDocument(
            id="terraform:plan:abc123",
            repo_url="https://github.com/user/repo.git",
            branch="main",
            commit_sha="abc123",
            terraform_dir="/terraform",
            terraform_version="1.5.0",
            plan_timestamp=datetime.now(timezone.utc),
            total_add=1,
            total_change=1,
            total_destroy=0,
            changes=changes,
            summary_text="Plan: 1 to add, 1 to change, 0 to destroy",
        )

        chunker = TerraformPlanChunker()
        chunks = chunker.chunk(doc)

        # Should have summary + 2 change chunks
        assert len(chunks) == 3
        assert chunks[0].heading == "Terraform Plan Summary"
        assert "1 to add, 1 to change" in chunks[0].text
        assert chunks[0].properties["total_add"] == 1
        assert chunks[0].properties["total_change"] == 1

        # Check change chunks
        assert chunks[1].heading.startswith("Plan Change: create")
        assert chunks[2].heading.startswith("Plan Change: update")

    def test_chunk_plan_change_details(self):
        """Test chunking individual plan changes."""
        changes = [
            PlannedChange(
                address="azurerm_public_ip.web",
                action="replace",
                resource_type="azurerm_public_ip",
                provider="azurerm",
                changed_attributes=["sku"],
                action_reason="replace_because_cannot_update",
            )
        ]

        doc = TerraformPlanDocument(
            id="terraform:plan:abc123",
            repo_url="https://github.com/user/repo.git",
            branch="main",
            commit_sha="abc123",
            terraform_dir="/terraform",
            terraform_version="1.5.0",
            plan_timestamp=datetime.now(timezone.utc),
            total_add=1,
            total_change=0,
            total_destroy=0,
            changes=changes,
        )

        chunker = TerraformPlanChunker()
        chunks = chunker.chunk(doc)

        # Check change chunk details
        change_chunk = chunks[1]
        assert "Action: REPLACE" in change_chunk.text
        assert "azurerm_public_ip.web" in change_chunk.text
        assert "replace_because_cannot_update" in change_chunk.text
        assert change_chunk.properties["action"] == "replace"


class TestGitCommitChunker:
    """Test suite for GitCommitChunker."""

    def test_chunk_commit(self):
        """Test chunking a Git commit."""
        file_changes = [
            GitFileChange(
                path="main.tf",
                change_type="modify",
                additions=5,
                deletions=2,
            ),
            GitFileChange(
                path="variables.tf",
                change_type="add",
                additions=10,
                deletions=0,
            ),
        ]

        doc = GitCommitDocument(
            id="commit:abc123",
            sha="abc123def456",
            short_sha="abc123d",
            repo_url="https://github.com/user/repo.git",
            branch="main",
            message="Update Terraform configuration\n\nAdded new variables",
            message_subject="Update Terraform configuration",
            message_body="Added new variables",
            author_name="Jane Doe",
            author_email="jane@example.com",
            author_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            committer_name="Jane Doe",
            committer_email="jane@example.com",
            commit_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            files_changed=file_changes,
            total_additions=15,
            total_deletions=2,
            terraform_files_changed=["main.tf", "variables.tf"],
            has_terraform_changes=True,
        )

        chunker = GitCommitChunker()
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        assert chunks[0].doc_id == doc.id
        assert chunks[0].heading.startswith("Commit abc123d:")
        assert "Jane Doe" in chunks[0].text
        assert "15+ 2-" in chunks[0].text
        assert chunks[0].properties["has_terraform_changes"] is True

    def test_chunk_commit_with_many_files(self):
        """Test chunking commit with many file changes."""
        file_changes = [
            GitFileChange(
                path=f"file_{i}.tf",
                change_type="modify",
                additions=1,
                deletions=0,
            )
            for i in range(50)
        ]

        doc = GitCommitDocument(
            id="commit:abc123",
            sha="abc123def456",
            short_sha="abc123d",
            repo_url="https://github.com/user/repo.git",
            branch="main",
            message="Mass update",
            message_subject="Mass update",
            message_body="",
            author_name="Jane Doe",
            author_email="jane@example.com",
            author_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            committer_name="Jane Doe",
            committer_email="jane@example.com",
            commit_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            files_changed=file_changes,
            total_additions=50,
            total_deletions=0,
            terraform_files_changed=[f"file_{i}.tf" for i in range(50)],
            has_terraform_changes=True,
        )

        chunker = GitCommitChunker(max_files_per_chunk=20)
        chunks = chunker.chunk(doc)

        # Should have main chunk + 3 file chunks (50 files / 20 per chunk = 3)
        assert len(chunks) == 4
        assert chunks[0].heading.startswith("Commit abc123d: Mass update")


class TestChunkModel:
    """Test suite for Chunk model."""

    def test_create_chunk(self):
        """Test creating a chunk."""
        from src.indexing.models import Chunk

        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="azure_resource",
            text="Test chunk text",
            heading="Test Heading",
            chunk_index=0,
            total_chunks=1,
            resource_type="Microsoft.Compute/virtualMachines",
            resource_name="vm-1",
            tags={"Environment": "test"},
            properties={"key": "value"},
        )

        assert chunk.chunk_id == "doc-1:chunk:0"
        assert chunk.doc_id == "doc-1"
        assert chunk.text == "Test chunk text"
        assert chunk.tags == {"Environment": "test"}
        assert str(chunk).startswith("Chunk(doc-1:chunk:0):")

    def test_chunk_string_truncation(self):
        """Test chunk string representation truncates long text."""
        from src.indexing.models import Chunk

        long_text = "x" * 200
        chunk = Chunk(
            chunk_id="doc-1:chunk:0",
            doc_id="doc-1",
            doc_type="test",
            text=long_text,
            chunk_index=0,
            total_chunks=1,
        )

        chunk_str = str(chunk)
        assert len(chunk_str) < len(long_text) + 50  # Should be truncated
        assert "..." in chunk_str
