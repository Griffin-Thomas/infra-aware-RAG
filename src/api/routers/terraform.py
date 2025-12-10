"""Terraform API router."""

import logging
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_terraform_service
from src.api.models.terraform import (
    TerraformResource,
    TerraformPlan,
    PlanAnalysis,
    ParsedPlan,
)
from src.api.services.terraform_service import TerraformService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/terraform", tags=["terraform"])


@router.get("/resources", response_model=list[TerraformResource])
async def list_terraform_resources(
    repo_url: str | None = Query(default=None, description="Filter by repository URL"),
    type: str | None = Query(default=None, description="Filter by resource type"),
    file_path: str | None = Query(default=None, description="Filter by file path"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of results"),
    terraform_service: TerraformService = Depends(get_terraform_service),
):
    """
    List Terraform resources with optional filters.

    Returns a list of Terraform resource definitions from your IaC codebase.

    **Filters:**
    - `repo_url`: Filter by Git repository
    - `type`: Filter by resource type (e.g., "azurerm_virtual_machine")
    - `file_path`: Filter by file path (e.g., "infrastructure/compute.tf")

    **Use cases:**
    - "Show me all VM resources"
    - "List resources in the compute.tf file"
    - "Find all resources in a specific repository"
    """
    logger.info(f"Listing Terraform resources: repo_url={repo_url}, type={type}, file_path={file_path}, limit={limit}")

    try:
        resources = await terraform_service.list_resources(
            repo_url=repo_url,
            resource_type=type,
            file_path=file_path,
            limit=limit,
        )

        logger.info(f"Found {len(resources)} Terraform resources")
        return resources

    except Exception as e:
        logger.error(f"Failed to list Terraform resources: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to list Terraform resources. Please try again later.",
        )


@router.get("/resources/{address:path}", response_model=TerraformResource)
async def get_terraform_resource(
    address: str,
    repo_url: str = Query(..., description="Repository URL"),
    terraform_service: TerraformService = Depends(get_terraform_service),
):
    """
    Get a specific Terraform resource by address.

    The address should be the full Terraform resource address.

    **Example:**
    ```
    azurerm_virtual_machine.example
    module.networking.azurerm_virtual_network.main
    ```

    **Query parameters:**
    - `repo_url`: Required - Git repository URL to scope the search
    """
    logger.info(f"Fetching Terraform resource: {address} from {repo_url}")

    try:
        resource = await terraform_service.get_resource(address, repo_url)

        if not resource:
            raise HTTPException(
                status_code=404,
                detail=f"Terraform resource not found: {address} in {repo_url}",
            )

        return resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Terraform resource: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch Terraform resource. Please try again later.",
        )


@router.get("/plans", response_model=list[TerraformPlan])
async def list_terraform_plans(
    repo_url: str | None = Query(default=None, description="Filter by repository URL"),
    since: datetime | None = Query(default=None, description="Filter plans after this timestamp"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of results"),
    terraform_service: TerraformService = Depends(get_terraform_service),
):
    """
    List recent Terraform plans.

    Returns a list of Terraform plans with summaries of planned changes.

    **Filters:**
    - `repo_url`: Filter by Git repository
    - `since`: Filter plans created after this timestamp

    **Use cases:**
    - "Show me recent Terraform plans"
    - "What changes are planned for the prod environment?"
    - "Show me all plans from the last week"
    """
    logger.info(f"Listing Terraform plans: repo_url={repo_url}, since={since}, limit={limit}")

    try:
        plans = await terraform_service.list_plans(
            repo_url=repo_url,
            since=since,
            limit=limit,
        )

        logger.info(f"Found {len(plans)} Terraform plans")
        return plans

    except Exception as e:
        logger.error(f"Failed to list Terraform plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to list Terraform plans. Please try again later.",
        )


@router.get("/plans/{plan_id}", response_model=TerraformPlan)
async def get_terraform_plan(
    plan_id: str,
    terraform_service: TerraformService = Depends(get_terraform_service),
):
    """
    Get full details for a Terraform plan.

    Returns complete plan details including all planned changes.

    **Use cases:**
    - "Show me the details of plan XYZ"
    - "What will change in this plan?"
    """
    logger.info(f"Fetching Terraform plan: {plan_id}")

    try:
        plan = await terraform_service.get_plan(plan_id)

        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")

        return plan

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Terraform plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch Terraform plan. Please try again later.",
        )


@router.post("/plans/{plan_id}/analyze", response_model=PlanAnalysis)
async def analyze_terraform_plan(
    plan_id: str,
    terraform_service: TerraformService = Depends(get_terraform_service),
):
    """
    Get AI-generated analysis of a Terraform plan.

    Returns a summary of what will change, risk assessment,
    and recommendations for the plan.

    **Analysis includes:**
    - Summary of planned changes
    - Risk level (low, medium, high)
    - Key changes to review
    - Recommendations for safer execution

    **Use cases:**
    - "What's the risk of applying this plan?"
    - "Should I be worried about this plan?"
    - "What are the main changes in this plan?"
    """
    logger.info(f"Analyzing Terraform plan: {plan_id}")

    try:
        plan = await terraform_service.get_plan(plan_id)

        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")

        analysis = await terraform_service.analyze_plan(plan)

        logger.info(f"Generated analysis for plan {plan_id}: risk_level={analysis.risk_level}")
        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze Terraform plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze Terraform plan. Please try again later.",
        )


@router.post("/plans/parse", response_model=ParsedPlan)
async def parse_terraform_plan(
    plan_json: dict[str, Any],
    terraform_service: TerraformService = Depends(get_terraform_service),
):
    """
    Parse a Terraform plan JSON and return structured changes.

    Accepts the output of `terraform show -json plan.tfplan` and returns
    a structured representation of the planned changes.

    **Example usage:**
    ```bash
    terraform plan -out=plan.tfplan
    terraform show -json plan.tfplan > plan.json
    # POST plan.json to this endpoint
    ```

    **Returns:**
    - Count of resources to add, change, and destroy
    - Detailed list of all planned changes

    **Use cases:**
    - "Parse this Terraform plan file"
    - "What changes are in this plan?"
    - "Upload and analyze a local plan file"
    """
    logger.info("Parsing uploaded Terraform plan JSON")

    try:
        # parse_plan is synchronous, not async
        parsed = terraform_service.parse_plan(plan_json)

        logger.info(
            f"Parsed plan: add={parsed.add}, change={parsed.change}, destroy={parsed.destroy}"
        )
        return parsed

    except ValueError as e:
        # Invalid plan JSON
        logger.warning(f"Invalid Terraform plan JSON: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to parse Terraform plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to parse Terraform plan. Please try again later.",
        )
