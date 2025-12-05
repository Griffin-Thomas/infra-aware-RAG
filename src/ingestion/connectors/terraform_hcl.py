"""Terraform HCL file parser connector."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hcl2

from src.models.documents import TerraformResourceDocument

logger = logging.getLogger(__name__)


@dataclass
class ParsedTerraformFile:
    """Result of parsing a Terraform file."""

    path: str
    resources: list[dict[str, Any]] = field(default_factory=list)
    data_sources: list[dict[str, Any]] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    locals: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    providers: list[dict[str, Any]] = field(default_factory=list)
    terraform_block: dict[str, Any] | None = None


class TerraformHCLConnector:
    """Connector for parsing Terraform HCL files.

    This connector parses both .tf (HCL2) and .tf.json files, extracting
    resources, data sources, variables, outputs, locals, modules, and providers.
    """

    TERRAFORM_EXTENSIONS = {".tf", ".tf.json"}

    def __init__(self, base_path: Path | str):
        """Initialize the connector.

        Args:
            base_path: Base directory to search for Terraform files
        """
        self.base_path = Path(base_path)

        if not self.base_path.exists():
            raise ValueError(f"Base path does not exist: {self.base_path}")

        if not self.base_path.is_dir():
            raise ValueError(f"Base path is not a directory: {self.base_path}")

    def find_terraform_files(self) -> list[Path]:
        """Find all Terraform files in the base path recursively.

        Returns:
            Sorted list of Terraform file paths
        """
        files = []
        for ext in self.TERRAFORM_EXTENSIONS:
            files.extend(self.base_path.rglob(f"*{ext}"))

        # Filter out .terraform directory
        files = [f for f in files if ".terraform" not in f.parts]

        return sorted(files)

    def parse_file(self, file_path: Path) -> ParsedTerraformFile:
        """Parse a single Terraform file.

        Args:
            file_path: Path to the Terraform file

        Returns:
            ParsedTerraformFile with extracted components

        Raises:
            ValueError: If file cannot be parsed
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix == ".json":
                    content = json.load(f)
                else:
                    content = hcl2.load(f)

            relative_path = str(file_path.relative_to(self.base_path))

            return ParsedTerraformFile(
                path=relative_path,
                resources=self._extract_resources(content),
                data_sources=self._extract_data_sources(content),
                variables=self._extract_variables(content),
                outputs=self._extract_outputs(content),
                locals=content.get("locals", [{}])[0] if content.get("locals") else {},
                modules=self._extract_modules(content),
                providers=self._extract_providers(content),
                terraform_block=(
                    content.get("terraform", [{}])[0] if content.get("terraform") else None
                ),
            )

        except Exception as e:
            logger.error(f"Failed to parse Terraform file {file_path}: {e}")
            raise ValueError(f"Failed to parse {file_path}: {e}") from e

    def parse_all(self) -> list[ParsedTerraformFile]:
        """Parse all Terraform files in the base path.

        Returns:
            List of parsed Terraform files
        """
        files = self.find_terraform_files()
        logger.info(f"Found {len(files)} Terraform files in {self.base_path}")

        parsed_files = []
        for file_path in files:
            try:
                parsed = self.parse_file(file_path)
                parsed_files.append(parsed)
                logger.debug(f"Parsed {file_path}: {len(parsed.resources)} resources")
            except ValueError as e:
                logger.warning(f"Skipping file due to parse error: {e}")
                continue

        return parsed_files

    def _extract_resources(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract resource blocks from parsed HCL.

        Args:
            content: Parsed HCL content

        Returns:
            List of resource dictionaries
        """
        resources = []
        for resource_block in content.get("resource", []):
            for resource_type, instances in resource_block.items():
                for name, config in instances.items():
                    resources.append(
                        {
                            "type": resource_type,
                            "name": name,
                            "config": config,
                            "address": f"{resource_type}.{name}",
                        }
                    )
        return resources

    def _extract_data_sources(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract data source blocks from parsed HCL.

        Args:
            content: Parsed HCL content

        Returns:
            List of data source dictionaries
        """
        data_sources = []
        for data_block in content.get("data", []):
            for data_type, instances in data_block.items():
                for name, config in instances.items():
                    data_sources.append(
                        {
                            "type": data_type,
                            "name": name,
                            "config": config,
                            "address": f"data.{data_type}.{name}",
                        }
                    )
        return data_sources

    def _extract_variables(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract variable blocks from parsed HCL.

        Args:
            content: Parsed HCL content

        Returns:
            List of variable dictionaries
        """
        variables = []
        for var_block in content.get("variable", []):
            for name, config in var_block.items():
                variables.append(
                    {
                        "name": name,
                        "type": config.get("type"),
                        "default": config.get("default"),
                        "description": config.get("description"),
                        "sensitive": config.get("sensitive", [False])[0]
                        if isinstance(config.get("sensitive"), list)
                        else config.get("sensitive", False),
                    }
                )
        return variables

    def _extract_outputs(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract output blocks from parsed HCL.

        Args:
            content: Parsed HCL content

        Returns:
            List of output dictionaries
        """
        outputs = []
        for output_block in content.get("output", []):
            for name, config in output_block.items():
                outputs.append(
                    {
                        "name": name,
                        "value": config.get("value"),
                        "description": config.get("description"),
                        "sensitive": config.get("sensitive", [False])[0]
                        if isinstance(config.get("sensitive"), list)
                        else config.get("sensitive", False),
                    }
                )
        return outputs

    def _extract_modules(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract module blocks from parsed HCL.

        Args:
            content: Parsed HCL content

        Returns:
            List of module dictionaries
        """
        modules = []
        for module_block in content.get("module", []):
            for name, config in module_block.items():
                modules.append(
                    {
                        "name": name,
                        "source": config.get("source"),
                        "version": config.get("version"),
                        "config": {
                            k: v for k, v in config.items() if k not in ("source", "version")
                        },
                    }
                )
        return modules

    def _extract_providers(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract provider blocks from parsed HCL.

        Args:
            content: Parsed HCL content

        Returns:
            List of provider dictionaries
        """
        providers = []
        for provider_block in content.get("provider", []):
            for name, config in provider_block.items():
                providers.append(
                    {"name": name, "alias": config.get("alias"), "config": config}
                )
        return providers

    def extract_dependencies(self, resource_config: dict[str, Any]) -> list[str]:
        """Extract both explicit and implicit dependencies from a resource.

        Args:
            resource_config: Resource configuration dictionary

        Returns:
            List of dependency addresses
        """
        dependencies = []

        # Explicit depends_on
        depends_on = resource_config.get("depends_on", [])
        if isinstance(depends_on, list):
            dependencies.extend(depends_on)

        # Implicit dependencies through references
        # This is a simplified version - in reality, would need to parse
        # all attribute values looking for ${resource_type.name.attr} patterns
        implicit = self._find_resource_references(resource_config)
        dependencies.extend(implicit)

        return list(set(dependencies))  # Remove duplicates

    def _find_resource_references(
        self, obj: Any, references: list[str] | None = None
    ) -> list[str]:
        """Recursively find resource references in configuration.

        Args:
            obj: Object to search (dict, list, or primitive)
            references: Accumulated list of references

        Returns:
            List of resource reference addresses
        """
        if references is None:
            references = []

        if isinstance(obj, dict):
            for value in obj.values():
                self._find_resource_references(value, references)
        elif isinstance(obj, list):
            for item in obj:
                self._find_resource_references(item, references)
        elif isinstance(obj, str):
            # Simple pattern matching for references like "azurerm_resource_group.main.name"
            # In a production system, would use proper HCL expression parsing
            if "." in obj and any(
                obj.startswith(prefix)
                for prefix in ["azurerm_", "aws_", "google_", "data.", "var.", "local."]
            ):
                # Extract the resource reference (first two parts)
                parts = obj.split(".")
                if len(parts) >= 2:
                    ref = f"{parts[0]}.{parts[1]}"
                    if ref not in references:
                        references.append(ref)

        return references

    def convert_to_document(
        self,
        resource: dict[str, Any],
        file_path: str,
        repo_url: str,
        branch: str,
        last_commit_sha: str,
        last_commit_date: Any,
        line_number: int = 1,
    ) -> TerraformResourceDocument:
        """Convert a parsed resource to a TerraformResourceDocument.

        Args:
            resource: Parsed resource dictionary
            file_path: Path to the file containing this resource
            repo_url: Git repository URL
            branch: Git branch
            last_commit_sha: Last commit that modified this file
            last_commit_date: Date of last commit
            line_number: Line number where resource starts (default 1)

        Returns:
            TerraformResourceDocument instance
        """
        resource_type = resource["type"]
        resource_name = resource["name"]
        address = resource["address"]

        # Extract provider from resource type (e.g., "azurerm" from "azurerm_virtual_network")
        provider = resource_type.split("_")[0] if "_" in resource_type else resource_type

        # Generate source code representation (simplified)
        source_code = self._generate_source_code(resource)

        # Extract dependencies
        dependencies = resource.get("config", {}).get("depends_on", [])
        implicit_deps = self._find_resource_references(resource.get("config", {}))

        doc = TerraformResourceDocument(
            id=f"{repo_url}:{file_path}:{address}",
            address=address,
            type=resource_type,
            name=resource_name,
            module_path=None,  # Would be populated if parsing module structure
            repo_url=repo_url,
            branch=branch,
            file_path=file_path,
            line_number=line_number,
            source_code=source_code,
            provider=provider,
            provider_version=None,  # Would be extracted from terraform block
            attributes=resource.get("config", {}),
            dependencies=dependencies if isinstance(dependencies, list) else [],
            implicit_dependencies=implicit_deps,
            last_commit_sha=last_commit_sha,
            last_commit_date=last_commit_date,
        )

        # Generate searchable text
        doc.searchable_text = doc.generate_searchable_text()

        return doc

    def _generate_source_code(self, resource: dict[str, Any]) -> str:
        """Generate a source code representation of a resource.

        Args:
            resource: Resource dictionary

        Returns:
            HCL-like string representation
        """
        resource_type = resource["type"]
        resource_name = resource["name"]
        config = resource.get("config", {})

        # Simple representation - in production would serialize back to proper HCL
        lines = [f'resource "{resource_type}" "{resource_name}" {{']

        for key, value in config.items():
            lines.append(f"  {key} = {self._format_value(value)}")

        lines.append("}")

        return "\n".join(lines)

    def _format_value(self, value: Any, indent: int = 0) -> str:
        """Format a value for HCL-like output.

        Args:
            value: Value to format
            indent: Current indentation level

        Returns:
            Formatted string
        """
        if isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            if not value:
                return "[]"
            items = [self._format_value(v, indent + 1) for v in value]
            return "[" + ", ".join(items) + "]"
        elif isinstance(value, dict):
            if not value:
                return "{}"
            return "{...}"  # Simplified for nested objects
        else:
            return str(value)
