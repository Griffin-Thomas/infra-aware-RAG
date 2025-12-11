"""Unit tests for Terraform plan connector."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.ingestion.connectors.terraform_plan import TerraformPlanConnector


@pytest.fixture
def fixtures_dir():
    """Get the fixtures directory path."""
    return Path(__file__).parent.parent / "fixtures" / "terraform"


@pytest.fixture
def connector():
    """Create a connector instance."""
    return TerraformPlanConnector()


class TestTerraformPlanConnector:
    """Test suite for TerraformPlanConnector."""

    def test_init(self, connector):
        """Test connector initialization."""
        assert connector is not None

    def test_parse_plan_file(self, connector, fixtures_dir):
        """Test parsing a plan file from disk."""
        plan_file = fixtures_dir / "plan.json"
        processed = connector.parse_plan_file(plan_file)

        assert processed["terraform_version"] == "1.5.0"
        assert len(processed["changes"]) == 5  # No-op excluded, read included
        assert processed["total_add"] == 2  # create + replace
        assert processed["total_change"] == 1  # update
        assert processed["total_destroy"] == 2  # delete + replace (replace counts as destroy+add)

    def test_parse_plan_file_not_found(self, connector, tmp_path):
        """Test error when plan file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            connector.parse_plan_file(nonexistent)

    def test_parse_plan_json(self, connector, fixtures_dir):
        """Test parsing plan from JSON string."""
        plan_file = fixtures_dir / "plan.json"
        with open(plan_file) as f:
            plan_json = f.read()

        processed = connector.parse_plan_json(plan_json)
        assert len(processed["changes"]) == 5

    def test_parse_invalid_json(self, connector):
        """Test error on invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            connector.parse_plan_json("not valid json")

    def test_process_change_create(self, connector):
        """Test processing a create action."""
        change = {
            "address": "azurerm_resource_group.test",
            "type": "azurerm_resource_group",
            "provider_name": "azurerm",
            "change": {
                "actions": ["create"],
                "before": None,
                "after": {"name": "rg-test", "location": "canadaeast"},
                "after_unknown": {"id": True},
            },
        }

        processed = connector._process_change(change)

        assert processed["action"] == "create"
        assert processed["address"] == "azurerm_resource_group.test"
        assert processed["resource_type"] == "azurerm_resource_group"
        assert processed["before"] is None
        assert processed["after"]["name"] == "rg-test"

    def test_process_change_update(self, connector):
        """Test processing an update action."""
        change = {
            "address": "azurerm_vnet.main",
            "type": "azurerm_virtual_network",
            "provider_name": "azurerm",
            "change": {
                "actions": ["update"],
                "before": {"name": "vnet-old"},
                "after": {"name": "vnet-new"},
                "after_unknown": {},
            },
        }

        processed = connector._process_change(change)
        assert processed["action"] == "update"
        assert "name" in processed["changed_attributes"]

    def test_process_change_delete(self, connector):
        """Test processing a delete action."""
        change = {
            "address": "azurerm_storage.old",
            "type": "azurerm_storage_account",
            "provider_name": "azurerm",
            "change": {
                "actions": ["delete"],
                "before": {"name": "storage-old"},
                "after": None,
                "after_unknown": {},
            },
        }

        processed = connector._process_change(change)
        assert processed["action"] == "delete"
        assert processed["after"] is None

    def test_process_change_replace(self, connector):
        """Test processing a replace action."""
        change = {
            "address": "azurerm_public_ip.web",
            "type": "azurerm_public_ip",
            "provider_name": "azurerm",
            "change": {
                "actions": ["delete", "create"],
                "before": {"sku": "Basic"},
                "after": {"sku": "Standard"},
                "after_unknown": {},
                "action_reason": "replace_because_cannot_update",
            },
        }

        processed = connector._process_change(change)
        assert processed["action"] == "replace"
        assert processed["action_reason"] == "replace_because_cannot_update"

    def test_process_change_no_op(self, connector):
        """Test that no-op changes are skipped."""
        change = {
            "address": "azurerm_subnet.unchanged",
            "type": "azurerm_subnet",
            "provider_name": "azurerm",
            "change": {
                "actions": ["no-op"],
                "before": {"name": "subnet-1"},
                "after": {"name": "subnet-1"},
            },
        }

        processed = connector._process_change(change)
        assert processed is None

    def test_find_changed_attributes(self, connector):
        """Test finding changed attributes."""
        before = {"name": "old-name", "size": "small", "tags": {"env": "dev"}}
        after = {"name": "new-name", "size": "small", "tags": {"env": "prod"}}

        changed = connector._find_changed_attributes(before, after)

        assert "name" in changed
        assert "tags.env" in changed
        assert "size" not in changed

    def test_find_changed_attributes_none(self, connector):
        """Test with None values."""
        changed = connector._find_changed_attributes(None, {"key": "value"})
        assert len(changed) == 0

        changed = connector._find_changed_attributes({"key": "value"}, None)
        assert len(changed) == 0

    def test_convert_to_document(self, connector, fixtures_dir):
        """Test converting plan to document."""
        plan_file = fixtures_dir / "plan.json"
        processed = connector.parse_plan_file(plan_file)

        doc = connector.convert_to_document(
            processed_plan=processed,
            plan_id="plan-123",
            repo_url="https://github.com/example/repo",
            branch="main",
            commit_sha="abc123",
            terraform_dir="/terraform",
            plan_timestamp=datetime(2024, 1, 15),
        )

        assert doc.id == "plan-123"
        assert doc.repo_url == "https://github.com/example/repo"
        assert doc.terraform_version == "1.5.0"
        assert doc.total_add == 2
        assert doc.total_change == 1
        assert doc.total_destroy == 2  # delete + replace (replace counts as destroy+add)
        assert len(doc.changes) == 5
        assert "Plan:" in doc.summary_text

    def test_action_counting(self, connector, fixtures_dir):
        """Test that actions are counted correctly."""
        plan_file = fixtures_dir / "plan.json"
        processed = connector.parse_plan_file(plan_file)

        # 1 create, 1 update, 1 delete, 1 replace (replace counts as both destroy+add)
        assert processed["total_add"] == 2  # create + replace
        assert processed["total_change"] == 1  # update
        assert processed["total_destroy"] == 2  # delete + replace
