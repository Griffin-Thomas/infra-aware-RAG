# Data Model JSON Schemas

This directory contains JSON schemas for all document models used in the Infra-Aware RAG system.

## Generating Schemas

To generate or regenerate the schemas:

```bash
# Install dependencies first
pip install -r requirements.txt

# Run the schema export script
python -m src.models.schema_export
```

## Available Schemas

The following schemas are exported:

- `AzureResourceDocument.json` - Azure resources from Resource Graph
- `TerraformResourceDocument.json` - Terraform resource definitions from HCL
- `TerraformStateDocument.json` - Terraform state files
- `TerraformStateResource.json` - Individual resources in state
- `TerraformPlanDocument.json` - Terraform plan outputs
- `PlannedChange.json` - Individual changes in a plan
- `GitCommitDocument.json` - Git commits
- `GitFileChange.json` - File changes in commits

## Usage

These schemas can be used for:
- API documentation
- Validating data before ingestion
- Generating client libraries
- Understanding the data structure
