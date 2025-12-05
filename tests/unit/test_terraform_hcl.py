"""Unit tests for Terraform HCL connector."""

from datetime import datetime
from pathlib import Path

import pytest

from src.ingestion.connectors.terraform_hcl import ParsedTerraformFile, TerraformHCLConnector


@pytest.fixture
def fixtures_dir():
    """Get the fixtures directory path."""
    return Path(__file__).parent.parent / "fixtures" / "terraform"


@pytest.fixture
def connector(fixtures_dir):
    """Create a connector instance for test fixtures."""
    return TerraformHCLConnector(fixtures_dir)


class TestTerraformHCLConnector:
    """Test suite for TerraformHCLConnector."""

    def test_init_with_valid_path(self, fixtures_dir):
        """Test connector initialization with valid path."""
        connector = TerraformHCLConnector(fixtures_dir)
        assert connector.base_path == fixtures_dir

    def test_init_with_string_path(self, fixtures_dir):
        """Test connector initialization with string path."""
        connector = TerraformHCLConnector(str(fixtures_dir))
        assert connector.base_path == fixtures_dir

    def test_init_with_nonexistent_path(self):
        """Test connector initialization with non-existent path."""
        with pytest.raises(ValueError, match="does not exist"):
            TerraformHCLConnector("/nonexistent/path")

    def test_init_with_file_path(self, fixtures_dir):
        """Test connector initialization with file instead of directory."""
        file_path = fixtures_dir / "main.tf"
        with pytest.raises(ValueError, match="not a directory"):
            TerraformHCLConnector(file_path)

    def test_find_terraform_files(self, connector):
        """Test finding Terraform files."""
        files = connector.find_terraform_files()

        assert len(files) >= 2
        assert any(f.name == "main.tf" for f in files)
        assert any(f.name == "config.tf.json" for f in files)

        # Verify all files have correct extensions
        for file in files:
            assert file.suffix in {".tf", ".json"}

    def test_parse_hcl_file(self, connector, fixtures_dir):
        """Test parsing a .tf file."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert isinstance(parsed, ParsedTerraformFile)
        assert parsed.path == "main.tf"

        # Check resources
        assert len(parsed.resources) == 3
        resource_types = [r["type"] for r in parsed.resources]
        assert "azurerm_resource_group" in resource_types
        assert "azurerm_virtual_network" in resource_types
        assert "azurerm_subnet" in resource_types

        # Check resource details
        rg_resource = next(r for r in parsed.resources if r["type"] == "azurerm_resource_group")
        assert rg_resource["name"] == "main"
        assert rg_resource["address"] == "azurerm_resource_group.main"
        assert "name" in rg_resource["config"]

    def test_parse_json_file(self, connector, fixtures_dir):
        """Test parsing a .tf.json file."""
        config_json = fixtures_dir / "config.tf.json"
        parsed = connector.parse_file(config_json)

        assert isinstance(parsed, ParsedTerraformFile)
        assert parsed.path == "config.tf.json"

        # Check resources
        assert len(parsed.resources) == 1
        assert parsed.resources[0]["type"] == "azurerm_storage_account"
        assert parsed.resources[0]["name"] == "example"

        # Check variables
        assert len(parsed.variables) == 1
        assert parsed.variables[0]["name"] == "storage_name"

    def test_extract_resources(self, connector, fixtures_dir):
        """Test resource extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.resources) == 3

        # Verify resource structure
        for resource in parsed.resources:
            assert "type" in resource
            assert "name" in resource
            assert "config" in resource
            assert "address" in resource

        # Check specific resource
        vnet = next(r for r in parsed.resources if r["type"] == "azurerm_virtual_network")
        assert vnet["name"] == "main"
        assert "address_space" in vnet["config"]

    def test_extract_data_sources(self, connector, fixtures_dir):
        """Test data source extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.data_sources) == 1
        data_source = parsed.data_sources[0]
        assert data_source["type"] == "azurerm_client_config"
        assert data_source["name"] == "current"
        assert data_source["address"] == "data.azurerm_client_config.current"

    def test_extract_variables(self, connector, fixtures_dir):
        """Test variable extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.variables) == 3

        # Check location variable
        location_var = next(v for v in parsed.variables if v["name"] == "location")
        assert location_var["type"] == "string"
        assert location_var["default"] == "canadaeast"
        assert location_var["description"] == "Azure region for resources"
        assert location_var["sensitive"] is False

        # Check sensitive variable
        password_var = next(v for v in parsed.variables if v["name"] == "admin_password")
        assert password_var["sensitive"] is True

    def test_extract_outputs(self, connector, fixtures_dir):
        """Test output extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.outputs) == 2

        # Check output with description
        rg_output = next(o for o in parsed.outputs if o["name"] == "resource_group_id")
        assert rg_output["description"] == "The ID of the resource group"
        assert "value" in rg_output

        # Check output without sensitive flag
        vnet_output = next(o for o in parsed.outputs if o["name"] == "vnet_id")
        assert vnet_output["sensitive"] is False

    def test_extract_locals(self, connector, fixtures_dir):
        """Test locals extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.locals) > 0
        assert "common_tags" in parsed.locals

    def test_extract_modules(self, connector, fixtures_dir):
        """Test module extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.modules) == 1
        module = parsed.modules[0]
        assert module["name"] == "storage"
        assert module["source"] == "./modules/storage"
        assert "resource_group_name" in module["config"]

    def test_extract_providers(self, connector, fixtures_dir):
        """Test provider extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert len(parsed.providers) == 1
        provider = parsed.providers[0]
        assert provider["name"] == "azurerm"
        assert "features" in provider["config"]

    def test_extract_terraform_block(self, connector, fixtures_dir):
        """Test terraform block extraction."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        assert parsed.terraform_block is not None
        assert "required_version" in parsed.terraform_block
        assert "required_providers" in parsed.terraform_block

    def test_parse_all(self, connector):
        """Test parsing all files."""
        parsed_files = connector.parse_all()

        assert len(parsed_files) >= 2
        assert any(f.path == "main.tf" for f in parsed_files)
        assert any(f.path == "config.tf.json" for f in parsed_files)

    def test_parse_invalid_file(self, connector, tmp_path):
        """Test parsing an invalid Terraform file."""
        invalid_file = tmp_path / "invalid.tf"
        invalid_file.write_text("this is not valid HCL {{{")

        with pytest.raises(ValueError, match="Failed to parse"):
            connector.parse_file(invalid_file)

    def test_extract_dependencies(self, connector):
        """Test dependency extraction."""
        resource_config = {
            "depends_on": ["azurerm_resource_group.main", "azurerm_virtual_network.main"]
        }

        deps = connector.extract_dependencies(resource_config)

        assert len(deps) >= 2
        assert "azurerm_resource_group.main" in deps
        assert "azurerm_virtual_network.main" in deps

    def test_find_resource_references(self, connector):
        """Test finding resource references in configuration."""
        config = {
            "resource_group_name": "azurerm_resource_group.main.name",
            "location": "var.location",
            "vnet_id": "azurerm_virtual_network.main.id",
            "nested": {"key": "data.azurerm_client_config.current.tenant_id"},
        }

        references = connector._find_resource_references(config)

        assert "azurerm_resource_group.main" in references
        assert "azurerm_virtual_network.main" in references
        assert "data.azurerm_client_config" in references
        assert "var.location" in references

    def test_convert_to_document(self, connector, fixtures_dir):
        """Test converting a resource to a document."""
        main_tf = fixtures_dir / "main.tf"
        parsed = connector.parse_file(main_tf)

        resource = parsed.resources[0]  # azurerm_resource_group.main

        doc = connector.convert_to_document(
            resource=resource,
            file_path="main.tf",
            repo_url="https://github.com/example/repo",
            branch="main",
            last_commit_sha="abc123",
            last_commit_date=datetime(2024, 1, 15),
            line_number=25,
        )

        assert doc.id == "https://github.com/example/repo:main.tf:azurerm_resource_group.main"
        assert doc.address == "azurerm_resource_group.main"
        assert doc.type == "azurerm_resource_group"
        assert doc.name == "main"
        assert doc.provider == "azurerm"
        assert doc.file_path == "main.tf"
        assert doc.line_number == 25
        assert doc.repo_url == "https://github.com/example/repo"
        assert doc.branch == "main"
        assert doc.last_commit_sha == "abc123"
        assert doc.source_code != ""
        assert doc.searchable_text != ""

    def test_generate_source_code(self, connector):
        """Test source code generation."""
        resource = {
            "type": "azurerm_resource_group",
            "name": "main",
            "config": {"name": "rg-test", "location": "canadaeast", "tags": {"env": "test"}},
        }

        source = connector._generate_source_code(resource)

        assert 'resource "azurerm_resource_group" "main"' in source
        assert "name" in source
        assert "location" in source
        assert "tags" in source

    def test_format_value(self, connector):
        """Test value formatting for HCL output."""
        assert connector._format_value("test") == '"test"'
        assert connector._format_value(True) == "true"
        assert connector._format_value(False) == "false"
        assert connector._format_value(42) == "42"
        assert connector._format_value(3.14) == "3.14"
        assert connector._format_value([1, 2, 3]) == "[1, 2, 3]"
        assert connector._format_value([]) == "[]"
        assert connector._format_value({}) == "{}"
        assert connector._format_value({"key": "value"}) == "{...}"

    def test_empty_file_parsing(self, connector, tmp_path):
        """Test parsing an empty Terraform file."""
        empty_file = tmp_path / "empty.tf"
        empty_file.write_text("")

        # Create a temporary connector for this test
        temp_connector = TerraformHCLConnector(tmp_path)
        parsed = temp_connector.parse_file(empty_file)

        assert parsed.path == "empty.tf"
        assert len(parsed.resources) == 0
        assert len(parsed.variables) == 0
        assert len(parsed.outputs) == 0
