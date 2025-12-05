"""Utility to export JSON schemas for documentation."""

import json
from pathlib import Path

from src.models.documents import (
    AzureResourceDocument,
    GitCommitDocument,
    GitFileChange,
    PlannedChange,
    TerraformPlanDocument,
    TerraformResourceDocument,
    TerraformStateDocument,
    TerraformStateResource,
)


def export_schemas(output_dir: str = "docs/schemas") -> None:
    """Export JSON schemas for all document models.

    Args:
        output_dir: Directory to write schema files to
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    models = [
        AzureResourceDocument,
        TerraformResourceDocument,
        TerraformStateDocument,
        TerraformStateResource,
        TerraformPlanDocument,
        PlannedChange,
        GitCommitDocument,
        GitFileChange,
    ]

    for model in models:
        schema = model.model_json_schema()
        schema_file = output_path / f"{model.__name__}.json"

        with open(schema_file, "w") as f:
            json.dump(schema, f, indent=2)

        print(f"Exported schema: {schema_file}")


if __name__ == "__main__":
    export_schemas()
