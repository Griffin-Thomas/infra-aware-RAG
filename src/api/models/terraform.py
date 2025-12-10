"""Terraform API request and response models."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any


class TerraformResource(BaseModel):
    """Terraform resource model."""

    address: str = Field(..., description="Resource address (e.g., azurerm_virtual_machine.example)")
    type: str = Field(..., description="Resource type (e.g., azurerm_virtual_machine)")
    name: str = Field(..., description="Resource name")
    module_path: str | None = Field(default=None, description="Module path if in a module")
    file_path: str = Field(..., description="Path to .tf file")
    line_number: int = Field(..., description="Line number in file")
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field(..., description="Git branch")
    provider: str = Field(..., description="Provider (e.g., azurerm, aws)")
    source_code: str = Field(..., description="Resource source code")
    dependencies: list[str] = Field(default_factory=list, description="List of resource dependencies")
    azure_resource_id: str | None = Field(default=None, description="Linked Azure resource ID")


class PlannedChange(BaseModel):
    """A planned resource change."""

    address: str = Field(..., description="Resource address")
    action: str = Field(..., description="Action: create, update, delete, or replace")
    resource_type: str = Field(..., description="Resource type")
    changed_attributes: list[str] = Field(
        default_factory=list, description="List of attributes that will change"
    )
    summary: str = Field(..., description="Human-readable summary of the change")


class TerraformPlan(BaseModel):
    """Terraform plan model."""

    id: str = Field(..., description="Plan ID")
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field(..., description="Git branch")
    commit_sha: str = Field(..., description="Git commit SHA")
    timestamp: datetime = Field(..., description="Plan generation timestamp")
    add: int = Field(..., description="Number of resources to add")
    change: int = Field(..., description="Number of resources to change")
    destroy: int = Field(..., description="Number of resources to destroy")
    changes: list[PlannedChange] = Field(default_factory=list, description="List of planned changes")


class PlanAnalysis(BaseModel):
    """AI-generated plan analysis."""

    summary: str = Field(..., description="Overall summary of the plan")
    risk_level: str = Field(..., description="Risk level: low, medium, or high")
    key_changes: list[str] = Field(default_factory=list, description="List of key changes")
    recommendations: list[str] = Field(default_factory=list, description="List of recommendations")


class ParsedPlan(BaseModel):
    """Parsed Terraform plan result."""

    add: int = Field(..., description="Number of resources to add")
    change: int = Field(..., description="Number of resources to change")
    destroy: int = Field(..., description="Number of resources to destroy")
    changes: list[PlannedChange] = Field(default_factory=list, description="List of planned changes")
