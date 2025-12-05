"""Terraform plan parser for analyzing infrastructure changes."""

import json
import logging
from pathlib import Path
from typing import Any

from src.models.documents import PlannedChange, TerraformPlanDocument

logger = logging.getLogger(__name__)


class TerraformPlanConnector:
    """Connector for parsing Terraform plan output.

    Parses the JSON output from 'terraform plan -json' or 'terraform show -json planfile'.
    """

    def __init__(self):
        """Initialize the connector."""
        pass

    def parse_plan_file(self, path: Path) -> dict[str, Any]:
        """Parse a Terraform plan JSON file.

        Args:
            path: Path to the plan JSON file

        Returns:
            Processed plan dictionary

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        if not path.exists():
            raise FileNotFoundError(f"Plan file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        return self._process_plan(plan)

    def parse_plan_json(self, plan_json: str) -> dict[str, Any]:
        """Parse plan from JSON string.

        Args:
            plan_json: JSON string from terraform plan

        Returns:
            Processed plan dictionary
        """
        plan = json.loads(plan_json)
        return self._process_plan(plan)

    def _process_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Process and extract plan information.

        Args:
            plan: Raw plan dictionary from Terraform

        Returns:
            Processed plan with changes extracted
        """
        resource_changes = plan.get("resource_changes", [])
        changes = []

        total_add = 0
        total_change = 0
        total_destroy = 0

        for change in resource_changes:
            processed_change = self._process_change(change)
            if processed_change:
                changes.append(processed_change)

                # Count actions
                action = processed_change["action"]
                if action == "create":
                    total_add += 1
                elif action == "update":
                    total_change += 1
                elif action == "delete":
                    total_destroy += 1
                elif action == "replace":
                    total_add += 1
                    # Note: Terraform plan output shows replace as "+/-" but only counts as add in summary

        return {
            "terraform_version": plan.get("terraform_version", ""),
            "format_version": plan.get("format_version", ""),
            "changes": changes,
            "total_add": total_add,
            "total_change": total_change,
            "total_destroy": total_destroy,
        }

    def _process_change(self, change: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single resource change.

        Args:
            change: Resource change from plan

        Returns:
            Processed change dictionary or None if no-op
        """
        change_detail = change.get("change", {})
        actions = change_detail.get("actions", [])

        # Skip no-op changes
        if actions == ["no-op"]:
            return None

        # Determine primary action
        if "delete" in actions and "create" in actions:
            action = "replace"
        elif "create" in actions:
            action = "create"
        elif "delete" in actions:
            action = "delete"
        elif "update" in actions:
            action = "update"
        else:
            action = "no-op"

        # Extract resource info
        address = change.get("address", "")
        resource_type = change.get("type", "")
        provider_name = change.get("provider_name", "")

        # Get before and after states
        before = change_detail.get("before")
        after = change_detail.get("after")
        after_unknown = change_detail.get("after_unknown", {})

        # Find changed attributes
        changed_attrs = self._find_changed_attributes(before, after)

        return {
            "address": address,
            "action": action,
            "resource_type": resource_type,
            "provider": provider_name,
            "before": before,
            "after": after,
            "after_unknown": after_unknown,
            "changed_attributes": changed_attrs,
            "action_reason": change_detail.get("action_reason"),
        }

    def _find_changed_attributes(
        self, before: Any, after: Any, prefix: str = ""
    ) -> list[str]:
        """Find attributes that changed between before and after.

        Args:
            before: State before change
            after: State after change
            prefix: Current attribute path prefix

        Returns:
            List of changed attribute paths
        """
        changed = []

        if before is None or after is None:
            return []

        if not isinstance(before, dict) or not isinstance(after, dict):
            return []

        all_keys = set(before.keys()) | set(after.keys())

        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key

            before_val = before.get(key)
            after_val = after.get(key)

            if before_val != after_val:
                if isinstance(before_val, dict) and isinstance(after_val, dict):
                    changed.extend(self._find_changed_attributes(before_val, after_val, full_key))
                else:
                    changed.append(full_key)

        return changed

    def convert_to_document(
        self,
        processed_plan: dict[str, Any],
        plan_id: str,
        repo_url: str,
        branch: str,
        commit_sha: str,
        terraform_dir: str,
        plan_timestamp: Any,
    ) -> TerraformPlanDocument:
        """Convert processed plan to TerraformPlanDocument.

        Args:
            processed_plan: Processed plan from _process_plan()
            plan_id: Unique identifier for this plan
            repo_url: Git repository URL
            branch: Git branch
            commit_sha: Git commit SHA
            terraform_dir: Directory where plan was run
            plan_timestamp: When the plan was created

        Returns:
            TerraformPlanDocument instance
        """
        # Convert changes to PlannedChange objects
        changes = [
            PlannedChange(
                address=c["address"],
                action=c["action"],
                resource_type=c["resource_type"],
                provider=c["provider"],
                before=c.get("before"),
                after=c.get("after"),
                after_unknown=c.get("after_unknown"),
                changed_attributes=c.get("changed_attributes", []),
                action_reason=c.get("action_reason"),
            )
            for c in processed_plan["changes"]
        ]

        # Generate summary text
        summary_lines = [
            f"Plan: {processed_plan['total_add']} to add, "
            f"{processed_plan['total_change']} to change, "
            f"{processed_plan['total_destroy']} to destroy"
        ]

        if changes:
            summary_lines.append("\nChanges:")
            for change in changes[:10]:  # Show first 10
                summary_lines.append(f"  {change.action}: {change.address}")

        doc = TerraformPlanDocument(
            id=plan_id,
            repo_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
            terraform_dir=terraform_dir,
            terraform_version=processed_plan.get("terraform_version", ""),
            plan_timestamp=plan_timestamp,
            total_add=processed_plan["total_add"],
            total_change=processed_plan["total_change"],
            total_destroy=processed_plan["total_destroy"],
            changes=changes,
            summary_text="\n".join(summary_lines),
        )

        return doc
