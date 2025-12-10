"""Resource API request and response models."""

from pydantic import BaseModel, Field
from typing import Any


class AzureResource(BaseModel):
    """Azure resource model."""

    id: str = Field(..., description="Full Azure resource ID")
    name: str = Field(..., description="Resource name")
    type: str = Field(..., description="Resource type (e.g., Microsoft.Compute/virtualMachines)")
    resource_group: str = Field(..., description="Resource group name")
    subscription_id: str = Field(..., description="Subscription ID")
    subscription_name: str = Field(..., description="Subscription name")
    location: str = Field(..., description="Azure region")
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags")
    sku: dict[str, Any] | None = Field(default=None, description="SKU information")
    kind: str | None = Field(default=None, description="Resource kind")
    properties: dict[str, Any] = Field(default_factory=dict, description="Resource-specific properties")


class TerraformLink(BaseModel):
    """Terraform resource link."""

    address: str = Field(..., description="Terraform resource address (e.g., azurerm_virtual_machine.example)")
    type: str = Field(..., description="Terraform resource type")
    file_path: str = Field(..., description="Path to .tf file")
    line_number: int = Field(..., description="Line number in file")
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field(..., description="Git branch")
    source_code: str = Field(..., description="Source code snippet")


class ResourceDependency(BaseModel):
    """Resource dependency."""

    id: str = Field(..., description="Azure resource ID")
    name: str = Field(..., description="Resource name")
    type: str = Field(..., description="Resource type")
    relationship: str = Field(..., description="Type of relationship (e.g., 'depends_on', 'part_of')")
    direction: str = Field(..., description="Direction: 'upstream' (this depends on it) or 'downstream' (it depends on this)")


class ResourceGraphQueryRequest(BaseModel):
    """Request model for Resource Graph KQL query."""

    query: str = Field(..., min_length=1, max_length=10000, description="KQL query string")
    subscriptions: list[str] | None = Field(
        default=None,
        description="List of subscription IDs to query (optional, defaults to all accessible subscriptions)",
    )


class ResourceGraphQueryResponse(BaseModel):
    """Response model for Resource Graph query."""

    results: list[dict[str, Any]] = Field(..., description="Query results")
    total_records: int = Field(..., description="Total number of records returned")
