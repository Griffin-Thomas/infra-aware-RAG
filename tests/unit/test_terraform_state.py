"""Unit tests for Terraform state connector."""

import json
from pathlib import Path

import pytest

from src.ingestion.connectors.terraform_state import TerraformStateConnector


@pytest.fixture
def fixtures_dir():
    """Get the fixtures directory path."""
    return Path(__file__).parent.parent / "fixtures" / "terraform"


@pytest.fixture
def connector():
    """Create a connector instance."""
    return TerraformStateConnector()


@pytest.fixture
def sample_state():
    """Sample Terraform state (v4)."""
    return {
        "version": 4,
        "terraform_version": "1.5.0",
        "serial": 10,
        "lineage": "test-lineage-123",
        "outputs": {
            "public_output": {"value": "public-value", "sensitive": False},
            "secret_output": {"value": "secret-value", "sensitive": True},
        },
        "resources": [
            {
                "mode": "managed",
                "type": "azurerm_resource_group",
                "name": "main",
                "provider": "provider[\"registry.terraform.io/hashicorp/azurerm\"]",
                "instances": [
                    {
                        "attributes": {
                            "id": "/subscriptions/123/resourceGroups/rg-test",
                            "name": "rg-test",
                            "location": "canadaeast",
                        },
                        "dependencies": [],
                    }
                ],
            },
            {
                "mode": "managed",
                "type": "azurerm_key_vault_secret",
                "name": "password",
                "provider": "provider[\"registry.terraform.io/hashicorp/azurerm\"]",
                "instances": [
                    {
                        "attributes": {
                            "id": "/subscriptions/123/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv/secrets/pwd",
                            "name": "pwd",
                            "value": "SecretPassword123!",
                            "content_type": "text/plain",
                        },
                        "dependencies": [],
                    }
                ],
            },
        ],
    }


class TestTerraformStateConnector:
    """Test suite for TerraformStateConnector."""

    def test_init(self, connector):
        """Test connector initialization."""
        assert connector is not None
        assert len(connector.SENSITIVE_PATTERNS) > 0

    def test_parse_state_file(self, connector, fixtures_dir):
        """Test parsing a state file from disk."""
        state_file = fixtures_dir / "terraform.tfstate"
        processed = connector.parse_state_file(state_file)

        assert processed["version"] == 4
        assert processed["terraform_version"] == "1.5.0"
        assert processed["serial"] == 42
        assert processed["lineage"] == "abc123-def456-ghi789"
        assert len(processed["resources"]) == 4
        assert len(processed["outputs"]) == 3

    def test_parse_state_file_not_found(self, connector, tmp_path):
        """Test error when state file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.tfstate"
        with pytest.raises(FileNotFoundError):
            connector.parse_state_file(nonexistent)

    def test_parse_state_json(self, connector, sample_state):
        """Test parsing state from JSON string."""
        state_json = json.dumps(sample_state)
        processed = connector.parse_state_json(state_json)

        assert processed["version"] == 4
        assert processed["terraform_version"] == "1.5.0"
        assert len(processed["resources"]) == 2

    def test_parse_invalid_json(self, connector):
        """Test error on invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            connector.parse_state_json("not valid json")

    def test_unsupported_version(self, connector):
        """Test error on unsupported state version."""
        old_state = {"version": 3, "resources": []}
        with pytest.raises(ValueError, match="not supported"):
            connector._process_state(old_state)

    def test_process_state(self, connector, sample_state):
        """Test state processing."""
        processed = connector._process_state(sample_state)

        assert processed["version"] == 4
        assert processed["terraform_version"] == "1.5.0"
        assert processed["serial"] == 10
        assert processed["lineage"] == "test-lineage-123"
        assert len(processed["resources"]) == 2
        assert "outputs" in processed

    def test_process_resource(self, connector):
        """Test resource processing."""
        resource = {
            "mode": "managed",
            "type": "azurerm_storage_account",
            "name": "example",
            "provider": "provider[\"registry.terraform.io/hashicorp/azurerm\"]",
            "instances": [
                {
                    "index_key": 0,
                    "attributes": {
                        "name": "storageacct",
                        "location": "canadaeast",
                        "access_key": "secret-key-123",
                    },
                    "dependencies": ["azurerm_resource_group.main"],
                }
            ],
        }

        processed = connector._process_resource(resource)

        assert processed["address"] == "azurerm_storage_account.example"
        assert processed["type"] == "azurerm_storage_account"
        assert processed["name"] == "example"
        assert processed["mode"] == "managed"
        assert len(processed["instances"]) == 1

        # Check that sensitive attributes were found
        instance = processed["instances"][0]
        assert "access_key" in instance["sensitive_attributes"]
        assert instance["attributes"]["access_key"] == "[REDACTED]"

    def test_find_sensitive_attributes(self, connector):
        """Test sensitive attribute detection."""
        attributes = {
            "name": "test-resource",
            "password": "secret123",
            "admin_password": "admin123",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "connection_string": "Server=tcp:test.database.windows.net",
            "nested": {"client_secret": "oauth-secret", "public_value": "not-secret"},
        }

        sensitive = connector._find_sensitive_attributes(attributes)

        assert "password" in sensitive
        assert "admin_password" in sensitive
        assert "access_key" in sensitive
        assert "nested.client_secret" in sensitive
        assert "name" not in sensitive
        assert "nested.public_value" not in sensitive

    def test_find_sensitive_attributes_nested(self, connector):
        """Test finding sensitive attributes in nested structures."""
        attributes = {
            "config": {
                "database": {"password": "db-pass", "host": "localhost"},
                "api": {"api_key": "key123", "url": "https://api.example.com"},
            }
        }

        sensitive = connector._find_sensitive_attributes(attributes)

        assert "config.database.password" in sensitive
        assert "config.api.api_key" in sensitive
        assert len([s for s in sensitive if "host" in s or "url" in s]) == 0

    def test_redact_sensitive(self, connector):
        """Test sensitive value redaction."""
        data = {
            "name": "resource-name",
            "password": "secret123",
            "location": "canadaeast",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
        }

        sensitive_paths = ["password", "access_key"]
        redacted = connector._redact_sensitive(data, sensitive_paths)

        assert redacted["name"] == "resource-name"
        assert redacted["location"] == "canadaeast"
        assert redacted["password"] == "[REDACTED]"
        assert redacted["access_key"] == "[REDACTED]"

    def test_redact_sensitive_nested(self, connector):
        """Test redacting nested sensitive values."""
        data = {
            "config": {
                "database": {"password": "db-pass", "host": "localhost"},
                "public_setting": "visible",
            }
        }

        sensitive_paths = ["config.database.password"]
        redacted = connector._redact_sensitive(data, sensitive_paths)

        assert redacted["config"]["public_setting"] == "visible"
        assert redacted["config"]["database"]["host"] == "localhost"
        assert redacted["config"]["database"]["password"] == "[REDACTED]"

    def test_process_outputs(self, connector):
        """Test output processing."""
        outputs = {
            "public_ip": {"value": "20.51.123.45", "sensitive": False},
            "admin_password": {"value": "secret123", "sensitive": True},
            "resource_id": {"value": "/subscriptions/123/resourceGroups/rg"},
        }

        processed = connector._process_outputs(outputs)

        assert processed["public_ip"]["value"] == "20.51.123.45"
        assert processed["public_ip"]["sensitive"] is False

        assert processed["admin_password"]["value"] == "[SENSITIVE]"
        assert processed["admin_password"]["sensitive"] is True

        assert processed["resource_id"]["sensitive"] is False

    def test_state_with_no_resources(self, connector):
        """Test processing state with no resources."""
        state = {
            "version": 4,
            "terraform_version": "1.5.0",
            "serial": 1,
            "lineage": "empty",
            "resources": [],
            "outputs": {},
        }

        processed = connector._process_state(state)

        assert len(processed["resources"]) == 0
        assert len(processed["outputs"]) == 0

    def test_convert_to_document(self, connector, sample_state):
        """Test converting processed state to document."""
        processed = connector._process_state(sample_state)

        doc = connector.convert_to_document(
            processed_state=processed,
            state_id="test-state-123",
            state_file_path="/path/to/terraform.tfstate",
            backend_type="local",
            workspace="default",
        )

        assert doc.id == "test-state-123"
        assert doc.state_file_path == "/path/to/terraform.tfstate"
        assert doc.backend_type == "local"
        assert doc.workspace == "default"
        assert doc.terraform_version == "1.5.0"
        assert doc.serial == 10
        assert doc.lineage == "test-lineage-123"
        assert len(doc.resources) == 2
        assert len(doc.outputs) == 2

    def test_convert_to_document_azurerm_backend(self, connector, sample_state):
        """Test document conversion with Azure backend."""
        processed = connector._process_state(sample_state)

        doc = connector.convert_to_document(
            processed_state=processed,
            state_id="azurerm:container:state.tfstate",
            state_file_path=None,
            backend_type="azurerm",
            workspace="production",
        )

        assert doc.backend_type == "azurerm"
        assert doc.workspace == "production"
        assert doc.state_file_path is None

    def test_end_to_end_with_fixture(self, connector, fixtures_dir):
        """Test complete flow with fixture file."""
        state_file = fixtures_dir / "terraform.tfstate"
        processed = connector.parse_state_file(state_file)

        # Verify sensitive data was redacted
        storage_resource = next(
            (r for r in processed["resources"] if r["type"] == "azurerm_storage_account"), None
        )
        assert storage_resource is not None

        instance = storage_resource["instances"][0]
        assert instance["attributes"]["primary_access_key"] == "[REDACTED]"
        assert instance["attributes"]["secondary_access_key"] == "[REDACTED]"
        assert instance["attributes"]["primary_connection_string"] == "[REDACTED]"

        # Verify sensitive output was marked
        assert processed["outputs"]["storage_account_key"]["value"] == "[SENSITIVE]"
        assert processed["outputs"]["storage_account_key"]["sensitive"] is True

        # Verify non-sensitive data is intact
        assert processed["outputs"]["public_ip"]["value"] == "20.51.123.45"
        assert processed["outputs"]["public_ip"]["sensitive"] is False

    def test_data_source_processing(self, connector, fixtures_dir):
        """Test processing data sources vs managed resources."""
        state_file = fixtures_dir / "terraform.tfstate"
        processed = connector.parse_state_file(state_file)

        # Find data source
        data_source = next(
            (r for r in processed["resources"] if r["mode"] == "data"), None
        )
        assert data_source is not None
        assert data_source["type"] == "azurerm_client_config"

        # Find managed resource
        managed_resource = next(
            (r for r in processed["resources"] if r["mode"] == "managed"), None
        )
        assert managed_resource is not None

    def test_multiple_instances(self, connector):
        """Test resource with multiple instances (count or for_each)."""
        resource = {
            "mode": "managed",
            "type": "azurerm_virtual_machine",
            "name": "web",
            "provider": "provider[\"registry.terraform.io/hashicorp/azurerm\"]",
            "instances": [
                {
                    "index_key": 0,
                    "attributes": {"name": "web-0", "location": "canadaeast"},
                    "dependencies": [],
                },
                {
                    "index_key": 1,
                    "attributes": {"name": "web-1", "location": "canadaeast"},
                    "dependencies": [],
                },
            ],
        }

        processed = connector._process_resource(resource)
        assert len(processed["instances"]) == 2
        assert processed["instances"][0]["index_key"] == 0
        assert processed["instances"][1]["index_key"] == 1
