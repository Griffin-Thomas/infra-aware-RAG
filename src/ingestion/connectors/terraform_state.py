"""Terraform state file parser with sensitive data redaction."""

import json
import logging
from pathlib import Path
from typing import Any

from src.models.documents import TerraformStateDocument, TerraformStateResource

logger = logging.getLogger(__name__)


class TerraformStateConnector:
    """Connector for reading and parsing Terraform state files.

    This connector parses Terraform state files (v4+) and automatically
    detects and redacts sensitive attributes like passwords, secrets, and keys.
    """

    # Attributes that commonly contain secrets
    SENSITIVE_PATTERNS = [
        "password",
        "secret",
        "key",
        "token",
        "credential",
        "private_key",
        "client_secret",
        "access_key",
        "sas_token",
        "api_key",
        "auth",
        "connection_string",
    ]

    def __init__(self):
        """Initialize the connector."""
        pass

    def parse_state_file(self, path: Path) -> dict[str, Any]:
        """Parse a local Terraform state file.

        Args:
            path: Path to the .tfstate file

        Returns:
            Processed and sanitized state dictionary

        Raises:
            ValueError: If state version is not supported
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        if not path.exists():
            raise FileNotFoundError(f"State file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)

        return self._process_state(state)

    def parse_state_json(self, state_json: str) -> dict[str, Any]:
        """Parse state from JSON string.

        Args:
            state_json: JSON string containing Terraform state

        Returns:
            Processed and sanitized state dictionary

        Raises:
            ValueError: If state version is not supported
            json.JSONDecodeError: If string is not valid JSON
        """
        state = json.loads(state_json)
        return self._process_state(state)

    def _process_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process and sanitize state data.

        Args:
            state: Raw state dictionary from Terraform

        Returns:
            Processed state with sensitive data redacted

        Raises:
            ValueError: If state version is not supported
        """
        version = state.get("version", 4)

        if version < 4:
            raise ValueError(f"State version {version} not supported (need v4+)")

        return {
            "version": version,
            "terraform_version": state.get("terraform_version"),
            "serial": state.get("serial"),
            "lineage": state.get("lineage"),
            "resources": [self._process_resource(r) for r in state.get("resources", [])],
            "outputs": self._process_outputs(state.get("outputs", {})),
        }

    def _process_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Process a single resource from state.

        Args:
            resource: Resource dictionary from state file

        Returns:
            Processed resource with sanitized attributes
        """
        instances = []

        for instance in resource.get("instances", []):
            attributes = instance.get("attributes", {})
            sensitive_attrs = self._find_sensitive_attributes(attributes)

            # Redact sensitive values
            sanitized_attrs = self._redact_sensitive(attributes, sensitive_attrs)

            instances.append(
                {
                    "index_key": instance.get("index_key"),
                    "attributes": sanitized_attrs,
                    "sensitive_attributes": sensitive_attrs,
                    "dependencies": instance.get("dependencies", []),
                }
            )

        resource_type = resource.get("type", "")
        resource_name = resource.get("name", "")
        address = f"{resource_type}.{resource_name}"

        return {
            "address": address,
            "module": resource.get("module"),
            "mode": resource.get("mode", "managed"),
            "type": resource_type,
            "name": resource_name,
            "provider": resource.get("provider"),
            "instances": instances,
        }

    def _find_sensitive_attributes(
        self, attributes: dict[str, Any], prefix: str = ""
    ) -> list[str]:
        """Find attributes that might contain sensitive data.

        Args:
            attributes: Dictionary of resource attributes
            prefix: Current path prefix for nested attributes

        Returns:
            List of attribute paths that are sensitive
        """
        sensitive = []

        for key, value in attributes.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # Check if key matches sensitive patterns
            key_lower = key.lower()
            if any(pattern in key_lower for pattern in self.SENSITIVE_PATTERNS):
                sensitive.append(full_key)

            # Recurse into nested dicts
            if isinstance(value, dict):
                sensitive.extend(self._find_sensitive_attributes(value, full_key))

        return sensitive

    def _redact_sensitive(
        self, data: dict[str, Any], sensitive_paths: list[str]
    ) -> dict[str, Any]:
        """Redact sensitive values from data.

        Args:
            data: Dictionary to redact
            sensitive_paths: List of paths to redact

        Returns:
            Dictionary with sensitive values replaced with [REDACTED]
        """
        result = {}

        for key, value in data.items():
            # Check if this key is in sensitive paths (at this level)
            if key in [p.split(".")[0] for p in sensitive_paths if "." not in p]:
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                # Get nested paths for this key
                nested_paths = [p[len(key) + 1 :] for p in sensitive_paths if p.startswith(f"{key}.")]
                result[key] = self._redact_sensitive(value, nested_paths)
            elif isinstance(value, list):
                # Handle lists (could contain dicts)
                result[key] = value  # Simplified - could recurse into list items
            else:
                result[key] = value

        return result

    def _process_outputs(self, outputs: dict[str, Any]) -> dict[str, Any]:
        """Process outputs, excluding sensitive ones.

        Args:
            outputs: Dictionary of Terraform outputs

        Returns:
            Dictionary with sensitive outputs marked
        """
        result = {}
        for name, output in outputs.items():
            if output.get("sensitive", False):
                result[name] = {"value": "[SENSITIVE]", "sensitive": True}
            else:
                result[name] = {"value": output.get("value"), "sensitive": False}
        return result

    def convert_to_document(
        self,
        processed_state: dict[str, Any],
        state_id: str,
        state_file_path: str | None = None,
        backend_type: str = "local",
        workspace: str = "default",
    ) -> TerraformStateDocument:
        """Convert processed state to a TerraformStateDocument.

        Args:
            processed_state: Processed state from _process_state()
            state_id: Unique identifier for this state
            state_file_path: Path to state file (for local backend)
            backend_type: Type of backend (local, azurerm, s3, etc.)
            workspace: Terraform workspace name

        Returns:
            TerraformStateDocument instance
        """
        # Convert resources to TerraformStateResource objects
        resources = []
        for resource_dict in processed_state.get("resources", []):
            # For each instance, create a resource entry
            for instance in resource_dict.get("instances", []):
                resources.append(
                    TerraformStateResource(
                        address=resource_dict["address"],
                        type=resource_dict["type"],
                        name=resource_dict["name"],
                        provider=resource_dict.get("provider", ""),
                        mode=resource_dict.get("mode", "managed"),
                        attributes=instance["attributes"],
                        sensitive_attributes=instance.get("sensitive_attributes", []),
                        dependencies=instance.get("dependencies", []),
                    )
                )

        doc = TerraformStateDocument(
            id=state_id,
            state_file_path=state_file_path,
            backend_type=backend_type,
            workspace=workspace,
            terraform_version=processed_state.get("terraform_version", ""),
            serial=processed_state.get("serial", 0),
            lineage=processed_state.get("lineage", ""),
            resources=resources,
            outputs=processed_state.get("outputs", {}),
        )

        return doc
