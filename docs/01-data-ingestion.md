# Phase 1: Data Ingestion

## Overview

This phase establishes the data collection pipelines that feed the Infra-Aware RAG system. We will build connectors for three primary data sources:

1. **Azure Resource Graph** - Current state of Azure resources
2. **Terraform** - Infrastructure-as-Code definitions and plans
3. **Git** - Version history and change context

By the end of this phase, we will have a unified data pipeline that continuously ingests infrastructure data into a normalized format ready for indexing.

---

## Scope

### In Scope
- Azure Resource Graph queries across multiple subscriptions
- Terraform HCL file parsing (`.tf` files)
- Terraform state file processing (`.tfstate`)
- Terraform plan output parsing (`terraform plan -json`)
- Git repository cloning and commit history extraction
- Unified data model for all sources
- Scheduled ingestion with incremental updates
- Basic data validation and error handling

### Out of Scope (Future Phases)
- Real-time Azure Event Grid streaming
- Terraform Cloud/Enterprise API integration
- Azure DevOps/GitHub Actions pipeline integration
- Custom provider support beyond AzureRM
- Drift detection between state and live resources

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Ingestion Orchestrator                               │
│                    (Scheduler + Job Queue + Workers)                         │
└─────────────────────────────────────────────────────────────────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│    Azure      │       │   Terraform   │       │      Git      │
│   Connector   │       │   Connector   │       │   Connector   │
└───────────────┘       └───────────────┘       └───────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│ Resource Graph│       │  HCL Parser   │       │  Git Clone    │
│    Client     │       │  State Reader │       │  History API  │
└───────────────┘       └───────────────┘       └───────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                    ┌───────────────────────┐
                    │   Data Transformer    │
                    │   (Normalization)     │
                    └───────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │    Document Store     │
                    │   (Cosmos DB NoSQL)   │
                    └───────────────────────┘
```

---

## Technology Decisions

### Azure Resource Graph Client

**Decision:** Use the official `azure-mgmt-resourcegraph` Python SDK with `azure-identity` for authentication.

**Rationale:**
- First-party SDK with Managed Identity support
- Handles pagination automatically
- Well-documented query language (Kusto subset)

**Alternatives Considered:**
- REST API directly: More flexibility but requires handling auth, pagination, retries
- Azure CLI wrapper: Simpler but not suitable for production services

### Terraform Parser

**Decision:** Use `python-hcl2` for HCL parsing and custom JSON parsing for state/plan files.

**Rationale:**
- `python-hcl2` handles HCL2 syntax (Terraform 0.12+)
- State and plan files are JSON, no special parser needed
- Avoids dependency on Terraform CLI for parsing

**Alternatives Considered:**
- `terraform show -json`: Requires Terraform installed, but provides canonical output
- `pyhcl`: Only supports HCL1, deprecated

### Git Integration

**Decision:** Use `GitPython` library for cloning and history traversal.

**Rationale:**
- Mature library with good performance
- Handles authentication (SSH, HTTPS)
- Memory-efficient for large repos

**Alternatives Considered:**
- `pygit2` (libgit2 bindings): Faster but harder to install
- Shell out to `git` CLI: Simpler but parsing output is fragile

### Job Queue

**Decision:** Azure Service Bus with competing consumers pattern.

**Rationale:**
- Native Azure service with Managed Identity
- Dead-letter queue for failed jobs
- Session support for ordered processing

**Alternatives Considered:**
- Azure Queue Storage: Simpler but fewer features
- Celery + Redis: More complex to operate

---

## Data Model

### Azure Resource Document

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

class AzureResourceDocument(BaseModel):
    """Document stored for each Azure resource."""

    # Identity
    id: str = Field(..., description="Azure Resource ID")
    doc_type: str = "azure_resource"

    # Core properties
    name: str
    type: str  # e.g., "Microsoft.Compute/virtualMachines"
    resource_group: str
    subscription_id: str
    subscription_name: str
    location: str

    # Metadata
    tags: dict[str, str] = Field(default_factory=dict)
    sku: dict[str, Any] | None = None
    kind: str | None = None
    managed_by: str | None = None

    # Full properties (for detailed queries)
    properties: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_time: datetime | None = None
    changed_time: datetime | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships (populated during enrichment)
    terraform_address: str | None = None
    parent_resource_id: str | None = None
    child_resource_ids: list[str] = Field(default_factory=list)

    # Searchable text (generated for embedding)
    searchable_text: str = ""

    def generate_searchable_text(self) -> str:
        """Generate text for embedding."""
        parts = [
            f"Azure Resource: {self.name}",
            f"Type: {self.type}",
            f"Resource Group: {self.resource_group}",
            f"Location: {self.location}",
        ]
        if self.tags:
            parts.append(f"Tags: {', '.join(f'{k}={v}' for k, v in self.tags.items())}")
        if self.sku:
            parts.append(f"SKU: {self.sku}")
        return "\n".join(parts)
```

### Terraform Resource Document

```python
class TerraformResourceDocument(BaseModel):
    """Document stored for each Terraform resource definition."""

    # Identity
    id: str = Field(..., description="Unique ID: {repo}:{path}:{address}")
    doc_type: str = "terraform_resource"

    # Resource identity
    address: str  # e.g., "module.network.azurerm_virtual_network.main"
    type: str     # e.g., "azurerm_virtual_network"
    name: str     # e.g., "main"
    module_path: str | None = None  # e.g., "module.network"

    # Source location
    repo_url: str
    branch: str
    file_path: str
    line_number: int
    source_code: str  # The HCL block

    # Terraform metadata
    provider: str  # e.g., "azurerm"
    provider_version: str | None = None

    # Configuration
    attributes: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)  # Explicit depends_on
    implicit_dependencies: list[str] = Field(default_factory=list)  # Reference-based

    # Relationships
    azure_resource_id: str | None = None  # Linked Azure resource

    # Timestamps
    last_commit_sha: str
    last_commit_date: datetime
    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    # Searchable text
    searchable_text: str = ""

    def generate_searchable_text(self) -> str:
        """Generate text for embedding."""
        return f"""Terraform Resource: {self.address}
Type: {self.type}
Provider: {self.provider}
File: {self.file_path}

Source Code:
{self.source_code}"""
```

### Terraform State Document

```python
class TerraformStateResource(BaseModel):
    """A resource from Terraform state file."""

    address: str
    type: str
    name: str
    provider: str
    mode: str  # "managed" or "data"

    # The actual resource attributes from state
    attributes: dict[str, Any]

    # Sensitive attributes (redacted)
    sensitive_attributes: list[str] = Field(default_factory=list)

    # Dependencies
    dependencies: list[str] = Field(default_factory=list)


class TerraformStateDocument(BaseModel):
    """Document for a Terraform state file."""

    id: str  # Unique ID based on backend + workspace
    doc_type: str = "terraform_state"

    # State identity
    state_file_path: str | None = None  # For local state
    backend_type: str  # "local", "azurerm", "s3", etc.
    workspace: str = "default"

    # State metadata
    terraform_version: str
    serial: int
    lineage: str

    # Resources in this state
    resources: list[TerraformStateResource]

    # Outputs (non-sensitive only)
    outputs: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    state_timestamp: datetime | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
```

### Terraform Plan Document

```python
class PlannedChange(BaseModel):
    """A single resource change from a Terraform plan."""

    address: str
    action: str  # "create", "update", "delete", "replace", "read", "no-op"

    # Resource type info
    resource_type: str
    provider: str

    # Change details
    before: dict[str, Any] | None = None  # Current state
    after: dict[str, Any] | None = None   # Planned state
    after_unknown: dict[str, Any] | None = None  # Values known after apply

    # Attribute-level changes
    changed_attributes: list[str] = Field(default_factory=list)

    # Why this action?
    action_reason: str | None = None  # e.g., "replace_because_cannot_update"


class TerraformPlanDocument(BaseModel):
    """Document for a Terraform plan."""

    id: str  # Unique plan ID
    doc_type: str = "terraform_plan"

    # Source
    repo_url: str
    branch: str
    commit_sha: str
    terraform_dir: str  # Directory where plan was run

    # Plan metadata
    terraform_version: str
    plan_timestamp: datetime

    # Changes summary
    total_add: int = 0
    total_change: int = 0
    total_destroy: int = 0

    # All changes
    changes: list[PlannedChange]

    # Human-readable summary
    summary_text: str = ""

    # Timestamps
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
```

### Git Commit Document

```python
class GitFileChange(BaseModel):
    """A single file change in a commit."""

    path: str
    change_type: str  # "add", "modify", "delete", "rename"
    old_path: str | None = None  # For renames
    additions: int = 0
    deletions: int = 0


class GitCommitDocument(BaseModel):
    """Document for a Git commit."""

    id: str  # "{repo_url}:{sha}"
    doc_type: str = "git_commit"

    # Commit identity
    sha: str
    short_sha: str

    # Repository
    repo_url: str
    branch: str

    # Commit metadata
    message: str
    message_subject: str  # First line
    message_body: str     # Rest of message

    # Author info
    author_name: str
    author_email: str
    author_date: datetime

    # Committer info (can differ from author)
    committer_name: str
    committer_email: str
    commit_date: datetime

    # Changes
    files_changed: list[GitFileChange]
    total_additions: int = 0
    total_deletions: int = 0

    # Terraform-specific
    terraform_files_changed: list[str] = Field(default_factory=list)
    has_terraform_changes: bool = False

    # Timestamps
    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    # Searchable text
    searchable_text: str = ""

    def generate_searchable_text(self) -> str:
        """Generate text for embedding."""
        files_str = "\n".join(f"  - {f.path} ({f.change_type})" for f in self.files_changed)
        return f"""Git Commit: {self.short_sha}
Author: {self.author_name} <{self.author_email}>
Date: {self.author_date.isoformat()}

{self.message}

Files Changed:
{files_str}"""
```

---

## Connector Implementations

### Azure Resource Graph Connector

```python
# src/ingestion/connectors/azure_resource_graph.py

import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.resourcegraph.aio import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions

class AzureResourceGraphConnector:
    """Connector for Azure Resource Graph queries."""

    # Default query to fetch all resources
    DEFAULT_QUERY = """
    Resources
    | project id, name, type, resourceGroup, subscriptionId, location,
              tags, sku, kind, managedBy, properties,
              createdTime, changedTime
    | order by id asc
    """

    def __init__(
        self,
        subscription_ids: list[str],
        credential: DefaultAzureCredential | None = None,
        page_size: int = 1000,
    ):
        self.subscription_ids = subscription_ids
        self.credential = credential or DefaultAzureCredential()
        self.page_size = page_size
        self._client: ResourceGraphClient | None = None

    async def __aenter__(self):
        self._client = ResourceGraphClient(self.credential)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.close()
        await self.credential.close()

    async def fetch_all_resources(
        self,
        query: str | None = None,
        resource_types: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        """
        Fetch all resources matching the query.

        Args:
            query: Custom KQL query (uses DEFAULT_QUERY if not provided)
            resource_types: Optional filter for specific resource types

        Yields:
            Resource dictionaries from Azure Resource Graph
        """
        if query is None:
            query = self.DEFAULT_QUERY

        if resource_types:
            type_filter = " or ".join(f"type == '{t}'" for t in resource_types)
            query = query.replace(
                "| order by id asc",
                f"| where {type_filter}\n| order by id asc"
            )

        skip_token = None

        while True:
            options = QueryRequestOptions(
                top=self.page_size,
                skip_token=skip_token,
            )

            request = QueryRequest(
                subscriptions=self.subscription_ids,
                query=query,
                options=options,
            )

            response = await self._client.resources(request)

            for row in response.data:
                yield row

            skip_token = response.skip_token
            if not skip_token:
                break

    async def fetch_resource_by_id(self, resource_id: str) -> dict | None:
        """Fetch a single resource by its ID."""
        query = f"""
        Resources
        | where id == '{resource_id}'
        | project id, name, type, resourceGroup, subscriptionId, location,
                  tags, sku, kind, managedBy, properties,
                  createdTime, changedTime
        """

        async for resource in self.fetch_all_resources(query=query):
            return resource
        return None

    async def fetch_resource_types(self) -> list[dict]:
        """Fetch summary of all resource types and counts."""
        query = """
        Resources
        | summarize count() by type
        | order by count_ desc
        """

        types = []
        async for row in self.fetch_all_resources(query=query):
            types.append(row)
        return types
```

### Terraform HCL Connector

```python
# src/ingestion/connectors/terraform_hcl.py

import hcl2
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ParsedTerraformFile:
    """Result of parsing a Terraform file."""
    path: str
    resources: list[dict]
    data_sources: list[dict]
    variables: list[dict]
    outputs: list[dict]
    locals: dict
    modules: list[dict]
    providers: list[dict]
    terraform_block: dict | None


class TerraformHCLConnector:
    """Connector for parsing Terraform HCL files."""

    TERRAFORM_EXTENSIONS = {".tf", ".tf.json"}

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    def find_terraform_files(self) -> list[Path]:
        """Find all Terraform files in the base path."""
        files = []
        for ext in self.TERRAFORM_EXTENSIONS:
            files.extend(self.base_path.rglob(f"*{ext}"))
        return sorted(files)

    def parse_file(self, file_path: Path) -> ParsedTerraformFile:
        """Parse a single Terraform file."""
        with open(file_path, "r") as f:
            if file_path.suffix == ".json":
                import json
                content = json.load(f)
            else:
                content = hcl2.load(f)

        return ParsedTerraformFile(
            path=str(file_path.relative_to(self.base_path)),
            resources=self._extract_resources(content),
            data_sources=self._extract_data_sources(content),
            variables=self._extract_variables(content),
            outputs=self._extract_outputs(content),
            locals=content.get("locals", [{}])[0] if content.get("locals") else {},
            modules=self._extract_modules(content),
            providers=self._extract_providers(content),
            terraform_block=content.get("terraform", [{}])[0] if content.get("terraform") else None,
        )

    def _extract_resources(self, content: dict) -> list[dict]:
        """Extract resource blocks from parsed HCL."""
        resources = []
        for resource_block in content.get("resource", []):
            for resource_type, instances in resource_block.items():
                for name, config in instances.items():
                    resources.append({
                        "type": resource_type,
                        "name": name,
                        "config": config,
                    })
        return resources

    def _extract_data_sources(self, content: dict) -> list[dict]:
        """Extract data source blocks from parsed HCL."""
        data_sources = []
        for data_block in content.get("data", []):
            for data_type, instances in data_block.items():
                for name, config in instances.items():
                    data_sources.append({
                        "type": data_type,
                        "name": name,
                        "config": config,
                    })
        return data_sources

    def _extract_variables(self, content: dict) -> list[dict]:
        """Extract variable blocks from parsed HCL."""
        variables = []
        for var_block in content.get("variable", []):
            for name, config in var_block.items():
                variables.append({
                    "name": name,
                    "type": config.get("type"),
                    "default": config.get("default"),
                    "description": config.get("description"),
                    "sensitive": config.get("sensitive", False),
                })
        return variables

    def _extract_outputs(self, content: dict) -> list[dict]:
        """Extract output blocks from parsed HCL."""
        outputs = []
        for output_block in content.get("output", []):
            for name, config in output_block.items():
                outputs.append({
                    "name": name,
                    "value": config.get("value"),
                    "description": config.get("description"),
                    "sensitive": config.get("sensitive", False),
                })
        return outputs

    def _extract_modules(self, content: dict) -> list[dict]:
        """Extract module blocks from parsed HCL."""
        modules = []
        for module_block in content.get("module", []):
            for name, config in module_block.items():
                modules.append({
                    "name": name,
                    "source": config.get("source"),
                    "version": config.get("version"),
                    "config": {k: v for k, v in config.items()
                              if k not in ("source", "version")},
                })
        return modules

    def _extract_providers(self, content: dict) -> list[dict]:
        """Extract provider blocks from parsed HCL."""
        providers = []
        for provider_block in content.get("provider", []):
            for name, config in provider_block.items():
                providers.append({
                    "name": name,
                    "alias": config.get("alias"),
                    "config": config,
                })
        return providers

    def parse_all(self) -> list[ParsedTerraformFile]:
        """Parse all Terraform files in the base path."""
        return [self.parse_file(f) for f in self.find_terraform_files()]
```

### Terraform State Connector

```python
# src/ingestion/connectors/terraform_state.py

import json
from pathlib import Path
from typing import Any

class TerraformStateConnector:
    """Connector for reading Terraform state files."""

    # Attributes that commonly contain secrets
    SENSITIVE_PATTERNS = [
        "password", "secret", "key", "token", "credential",
        "private_key", "client_secret", "access_key", "sas_token",
    ]

    def __init__(self):
        pass

    def parse_state_file(self, path: Path) -> dict:
        """Parse a local Terraform state file."""
        with open(path, "r") as f:
            state = json.load(f)
        return self._process_state(state)

    def parse_state_json(self, state_json: str) -> dict:
        """Parse state from JSON string."""
        state = json.loads(state_json)
        return self._process_state(state)

    def _process_state(self, state: dict) -> dict:
        """Process and sanitize state data."""
        version = state.get("version", 4)

        if version < 4:
            raise ValueError(f"State version {version} not supported (need v4+)")

        return {
            "version": version,
            "terraform_version": state.get("terraform_version"),
            "serial": state.get("serial"),
            "lineage": state.get("lineage"),
            "resources": [
                self._process_resource(r)
                for r in state.get("resources", [])
            ],
            "outputs": self._process_outputs(state.get("outputs", {})),
        }

    def _process_resource(self, resource: dict) -> dict:
        """Process a single resource from state."""
        instances = []

        for instance in resource.get("instances", []):
            attributes = instance.get("attributes", {})
            sensitive_attrs = self._find_sensitive_attributes(attributes)

            # Redact sensitive values
            sanitized_attrs = self._redact_sensitive(attributes, sensitive_attrs)

            instances.append({
                "index_key": instance.get("index_key"),
                "attributes": sanitized_attrs,
                "sensitive_attributes": sensitive_attrs,
                "dependencies": instance.get("dependencies", []),
            })

        return {
            "address": f"{resource.get('type')}.{resource.get('name')}",
            "module": resource.get("module"),
            "mode": resource.get("mode"),
            "type": resource.get("type"),
            "name": resource.get("name"),
            "provider": resource.get("provider"),
            "instances": instances,
        }

    def _find_sensitive_attributes(self, attributes: dict, prefix: str = "") -> list[str]:
        """Find attributes that might contain sensitive data."""
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

    def _redact_sensitive(self, data: dict, sensitive_paths: list[str]) -> dict:
        """Redact sensitive values from data."""
        result = {}

        for key, value in data.items():
            if key in [p.split(".")[0] for p in sensitive_paths if "." not in p or p.startswith(key)]:
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                nested_paths = [
                    p[len(key)+1:] for p in sensitive_paths
                    if p.startswith(f"{key}.")
                ]
                result[key] = self._redact_sensitive(value, nested_paths)
            else:
                result[key] = value

        return result

    def _process_outputs(self, outputs: dict) -> dict:
        """Process outputs, excluding sensitive ones."""
        result = {}
        for name, output in outputs.items():
            if output.get("sensitive", False):
                result[name] = {"value": "[SENSITIVE]", "sensitive": True}
            else:
                result[name] = {"value": output.get("value"), "sensitive": False}
        return result
```

### Git Connector

```python
# src/ingestion/connectors/git_connector.py

import git
from pathlib import Path
from datetime import datetime
from typing import Iterator
import tempfile
import shutil

class GitConnector:
    """Connector for Git repository operations."""

    def __init__(
        self,
        clone_base_path: Path | None = None,
        auth_token: str | None = None,
    ):
        self.clone_base_path = clone_base_path or Path(tempfile.mkdtemp())
        self.auth_token = auth_token
        self._repos: dict[str, git.Repo] = {}

    def clone_or_update(
        self,
        repo_url: str,
        branch: str = "main",
    ) -> git.Repo:
        """Clone a repository or update if already cloned."""
        repo_path = self._get_repo_path(repo_url)

        if repo_path.exists():
            repo = git.Repo(repo_path)
            origin = repo.remotes.origin
            origin.fetch()
            repo.git.checkout(branch)
            origin.pull()
            self._repos[repo_url] = repo
            return repo

        # Clone new repo
        clone_url = self._get_authenticated_url(repo_url)
        repo = git.Repo.clone_from(
            clone_url,
            repo_path,
            branch=branch,
        )
        self._repos[repo_url] = repo
        return repo

    def get_commits(
        self,
        repo_url: str,
        branch: str = "main",
        since: datetime | None = None,
        until: datetime | None = None,
        paths: list[str] | None = None,
        max_commits: int = 1000,
    ) -> Iterator[dict]:
        """
        Get commits from a repository.

        Args:
            repo_url: Repository URL
            branch: Branch to read from
            since: Only commits after this date
            until: Only commits before this date
            paths: Only commits touching these paths
            max_commits: Maximum number of commits to return

        Yields:
            Commit dictionaries
        """
        repo = self._repos.get(repo_url) or self.clone_or_update(repo_url, branch)

        kwargs = {"max_count": max_commits}
        if since:
            kwargs["since"] = since.isoformat()
        if until:
            kwargs["until"] = until.isoformat()
        if paths:
            kwargs["paths"] = paths

        for commit in repo.iter_commits(branch, **kwargs):
            yield self._process_commit(commit, repo_url, branch)

    def _process_commit(self, commit: git.Commit, repo_url: str, branch: str) -> dict:
        """Process a git commit into a dictionary."""
        # Get diff stats
        files_changed = []
        total_additions = 0
        total_deletions = 0

        if commit.parents:
            diffs = commit.parents[0].diff(commit, create_patch=False)
            for diff in diffs:
                change_type = self._get_change_type(diff)
                files_changed.append({
                    "path": diff.b_path or diff.a_path,
                    "change_type": change_type,
                    "old_path": diff.a_path if diff.renamed else None,
                })

            # Get stats
            stats = commit.stats.total
            total_additions = stats.get("insertions", 0)
            total_deletions = stats.get("deletions", 0)

        # Check for Terraform changes
        terraform_files = [
            f["path"] for f in files_changed
            if f["path"].endswith(".tf") or f["path"].endswith(".tf.json")
        ]

        return {
            "sha": commit.hexsha,
            "short_sha": commit.hexsha[:8],
            "repo_url": repo_url,
            "branch": branch,
            "message": commit.message.strip(),
            "message_subject": commit.message.split("\n")[0].strip(),
            "message_body": "\n".join(commit.message.split("\n")[1:]).strip(),
            "author_name": commit.author.name,
            "author_email": commit.author.email,
            "author_date": datetime.fromtimestamp(commit.authored_date),
            "committer_name": commit.committer.name,
            "committer_email": commit.committer.email,
            "commit_date": datetime.fromtimestamp(commit.committed_date),
            "files_changed": files_changed,
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "terraform_files_changed": terraform_files,
            "has_terraform_changes": len(terraform_files) > 0,
        }

    def _get_change_type(self, diff: git.Diff) -> str:
        """Determine the type of change from a diff."""
        if diff.new_file:
            return "add"
        elif diff.deleted_file:
            return "delete"
        elif diff.renamed:
            return "rename"
        else:
            return "modify"

    def _get_repo_path(self, repo_url: str) -> Path:
        """Get local path for a repo URL."""
        # Convert URL to a safe directory name
        safe_name = repo_url.replace("https://", "").replace("/", "_").replace(":", "_")
        return self.clone_base_path / safe_name

    def _get_authenticated_url(self, repo_url: str) -> str:
        """Add authentication to URL if token provided."""
        if not self.auth_token:
            return repo_url

        if "github.com" in repo_url:
            return repo_url.replace(
                "https://github.com",
                f"https://{self.auth_token}@github.com"
            )
        elif "dev.azure.com" in repo_url:
            return repo_url.replace(
                "https://dev.azure.com",
                f"https://{self.auth_token}@dev.azure.com"
            )
        return repo_url

    def get_file_content(
        self,
        repo_url: str,
        file_path: str,
        ref: str = "HEAD",
    ) -> str | None:
        """Get content of a file at a specific ref."""
        repo = self._repos.get(repo_url)
        if not repo:
            return None

        try:
            blob = repo.commit(ref).tree / file_path
            return blob.data_stream.read().decode("utf-8")
        except KeyError:
            return None

    def cleanup(self, repo_url: str | None = None):
        """Remove cloned repositories."""
        if repo_url:
            repo_path = self._get_repo_path(repo_url)
            if repo_path.exists():
                shutil.rmtree(repo_path)
            self._repos.pop(repo_url, None)
        else:
            shutil.rmtree(self.clone_base_path, ignore_errors=True)
            self._repos.clear()
```

---

## Ingestion Orchestrator

```python
# src/ingestion/orchestrator.py

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from azure.servicebus.aio import ServiceBusClient
from azure.cosmos.aio import CosmosClient

class IngestionJobType(str, Enum):
    AZURE_RESOURCES = "azure_resources"
    TERRAFORM_FILES = "terraform_files"
    TERRAFORM_STATE = "terraform_state"
    GIT_COMMITS = "git_commits"
    FULL_SYNC = "full_sync"


@dataclass
class IngestionJob:
    job_id: str
    job_type: IngestionJobType
    config: dict
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "pending"
    error: str | None = None
    stats: dict | None = None


class IngestionOrchestrator:
    """Orchestrates ingestion jobs across all connectors."""

    def __init__(
        self,
        service_bus_connection: str,
        cosmos_connection: str,
        cosmos_database: str,
    ):
        self.service_bus_connection = service_bus_connection
        self.cosmos_connection = cosmos_connection
        self.cosmos_database = cosmos_database

    async def schedule_job(self, job: IngestionJob):
        """Schedule an ingestion job to the queue."""
        async with ServiceBusClient.from_connection_string(
            self.service_bus_connection
        ) as client:
            sender = client.get_queue_sender("ingestion-jobs")
            async with sender:
                message = ServiceBusMessage(
                    body=json.dumps({
                        "job_id": job.job_id,
                        "job_type": job.job_type,
                        "config": job.config,
                    }),
                    message_id=job.job_id,
                )
                await sender.send_messages(message)

    async def process_jobs(self):
        """Process jobs from the queue (worker entry point)."""
        async with ServiceBusClient.from_connection_string(
            self.service_bus_connection
        ) as client:
            receiver = client.get_queue_receiver("ingestion-jobs")

            async with receiver:
                async for message in receiver:
                    try:
                        job_data = json.loads(str(message))
                        await self._execute_job(job_data)
                        await receiver.complete_message(message)
                    except Exception as e:
                        # Log error, message goes to dead letter after retries
                        print(f"Job failed: {e}")
                        await receiver.abandon_message(message)

    async def _execute_job(self, job_data: dict):
        """Execute a single ingestion job."""
        job_type = IngestionJobType(job_data["job_type"])
        config = job_data["config"]

        if job_type == IngestionJobType.AZURE_RESOURCES:
            await self._ingest_azure_resources(config)
        elif job_type == IngestionJobType.TERRAFORM_FILES:
            await self._ingest_terraform_files(config)
        elif job_type == IngestionJobType.GIT_COMMITS:
            await self._ingest_git_commits(config)
        elif job_type == IngestionJobType.FULL_SYNC:
            await self._full_sync(config)

    async def _ingest_azure_resources(self, config: dict):
        """Ingest resources from Azure Resource Graph."""
        subscription_ids = config["subscription_ids"]

        async with AzureResourceGraphConnector(subscription_ids) as connector:
            documents = []

            async for resource in connector.fetch_all_resources():
                doc = AzureResourceDocument(
                    id=resource["id"],
                    name=resource["name"],
                    type=resource["type"],
                    resource_group=resource["resourceGroup"],
                    subscription_id=resource["subscriptionId"],
                    subscription_name=config.get("subscription_names", {}).get(
                        resource["subscriptionId"], resource["subscriptionId"]
                    ),
                    location=resource["location"],
                    tags=resource.get("tags", {}),
                    sku=resource.get("sku"),
                    kind=resource.get("kind"),
                    managed_by=resource.get("managedBy"),
                    properties=resource.get("properties", {}),
                    created_time=resource.get("createdTime"),
                    changed_time=resource.get("changedTime"),
                )
                doc.searchable_text = doc.generate_searchable_text()
                documents.append(doc)

                # Batch write every 100 documents
                if len(documents) >= 100:
                    await self._write_documents(documents)
                    documents = []

            # Write remaining documents
            if documents:
                await self._write_documents(documents)

    async def _write_documents(self, documents: list):
        """Write documents to Cosmos DB."""
        async with CosmosClient(self.cosmos_connection) as client:
            database = client.get_database_client(self.cosmos_database)
            container = database.get_container_client("documents")

            for doc in documents:
                await container.upsert_item(doc.model_dump())
```

---

## Configuration

```yaml
# config/ingestion.yaml

# CRITICAL: All Azure resources for this project must be in Canada
# Valid values: "canadaeast" or "canadacentral"
azure_region: "canadaeast"

# Azure subscriptions to ingest
azure:
  subscriptions:
    - id: "00000000-0000-0000-0000-000000000001"
      name: "Production"
      enabled: true
    - id: "00000000-0000-0000-0000-000000000002"
      name: "Development"
      enabled: true

  # Resource types to ingest (empty = all)
  resource_types: []

  # Refresh interval in minutes
  refresh_interval: 15

# Git repositories with Terraform code
git:
  repositories:
    - url: "https://github.com/org/infra-prod"
      branch: "main"
      terraform_paths:
        - "terraform/"
        - "modules/"
      enabled: true

    - url: "https://dev.azure.com/org/project/_git/infra-dev"
      branch: "main"
      terraform_paths:
        - "infrastructure/"
      enabled: true

  # How far back to look for commits
  history_days: 90

  # Refresh interval in minutes
  refresh_interval: 30

# Terraform state backends
terraform:
  state_backends:
    - type: "azurerm"
      storage_account: "tfstateaccount"
      container: "tfstate"
      key_pattern: "*.tfstate"
      enabled: true

  # Parse terraform plan outputs
  parse_plans: true

# Scheduling
scheduling:
  # Full sync schedule (cron format)
  full_sync: "0 0 * * *"  # Daily at midnight

  # Incremental sync intervals
  azure_resources: "*/15 * * * *"  # Every 15 minutes
  git_commits: "*/30 * * * *"      # Every 30 minutes
  terraform_state: "0 * * * *"     # Every hour
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_terraform_hcl_connector.py

import pytest
from src.ingestion.connectors.terraform_hcl import TerraformHCLConnector

class TestTerraformHCLConnector:

    def test_parse_simple_resource(self, tmp_path):
        """Test parsing a simple resource block."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('''
resource "azurerm_resource_group" "main" {
  name     = "my-rg"
  location = "canadaeast"  # Must use canadaeast or canadacentral
  tags = {
    environment = "production"
  }
}
''')
        connector = TerraformHCLConnector(tmp_path)
        result = connector.parse_file(tf_file)

        assert len(result.resources) == 1
        assert result.resources[0]["type"] == "azurerm_resource_group"
        assert result.resources[0]["name"] == "main"

    def test_parse_module_reference(self, tmp_path):
        """Test parsing module blocks."""
        tf_file = tmp_path / "modules.tf"
        tf_file.write_text('''
module "network" {
  source  = "Azure/network/azurerm"
  version = "3.0.0"

  resource_group_name = azurerm_resource_group.main.name
  vnet_name          = "my-vnet"
}
''')
        connector = TerraformHCLConnector(tmp_path)
        result = connector.parse_file(tf_file)

        assert len(result.modules) == 1
        assert result.modules[0]["name"] == "network"
        assert result.modules[0]["source"] == "Azure/network/azurerm"

    def test_parse_variables_with_defaults(self, tmp_path):
        """Test parsing variables with various configurations."""
        tf_file = tmp_path / "variables.tf"
        tf_file.write_text('''
variable "environment" {
  type        = string
  description = "The deployment environment"
  default     = "development"
}

variable "admin_password" {
  type      = string
  sensitive = true
}
''')
        connector = TerraformHCLConnector(tmp_path)
        result = connector.parse_file(tf_file)

        assert len(result.variables) == 2
        assert result.variables[0]["default"] == "development"
        assert result.variables[1]["sensitive"] == True
```

### Integration Tests

```python
# tests/integration/test_azure_resource_graph.py

import pytest
from src.ingestion.connectors.azure_resource_graph import AzureResourceGraphConnector

@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_resources_from_azure(integration_config):
    """Test fetching resources from actual Azure subscription."""
    subscription_ids = integration_config["azure"]["subscription_ids"]

    async with AzureResourceGraphConnector(subscription_ids) as connector:
        resources = []
        async for resource in connector.fetch_all_resources():
            resources.append(resource)
            if len(resources) >= 10:  # Limit for test
                break

        assert len(resources) > 0
        assert all("id" in r for r in resources)
        assert all("type" in r for r in resources)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_specific_resource_type(integration_config):
    """Test querying for specific resource types."""
    subscription_ids = integration_config["azure"]["subscription_ids"]

    async with AzureResourceGraphConnector(subscription_ids) as connector:
        resources = []
        async for resource in connector.fetch_all_resources(
            resource_types=["Microsoft.Storage/storageAccounts"]
        ):
            resources.append(resource)

        # All returned resources should be storage accounts
        assert all(
            r["type"].lower() == "microsoft.storage/storageaccounts"
            for r in resources
        )
```

### End-to-End Tests

```python
# tests/e2e/test_full_ingestion.py

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_ingestion_pipeline(e2e_config):
    """Test complete ingestion from Azure to Cosmos DB."""
    orchestrator = IngestionOrchestrator(
        service_bus_connection=e2e_config["service_bus_connection"],
        cosmos_connection=e2e_config["cosmos_connection"],
        cosmos_database=e2e_config["cosmos_database"],
    )

    # Run ingestion
    job = IngestionJob(
        job_id="test-e2e-001",
        job_type=IngestionJobType.AZURE_RESOURCES,
        config={
            "subscription_ids": e2e_config["azure"]["subscription_ids"],
        },
        created_at=datetime.utcnow(),
    )

    await orchestrator._execute_job(job.__dict__)

    # Verify documents in Cosmos DB
    async with CosmosClient(e2e_config["cosmos_connection"]) as client:
        database = client.get_database_client(e2e_config["cosmos_database"])
        container = database.get_container_client("documents")

        query = "SELECT * FROM c WHERE c.doc_type = 'azure_resource'"
        documents = [doc async for doc in container.query_items(query)]

        assert len(documents) > 0
```

---

## Demo Strategy

### Demo 1: Azure Resource Ingestion
**Goal:** Show that we can pull resources from Azure and store them.

**Steps:**
1. Configure a test subscription
2. Run the Azure Resource Graph connector
3. Show documents in Cosmos DB
4. Query for specific resource types

**Expected Output:**
```json
{
  "id": "/subscriptions/.../resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm",
  "doc_type": "azure_resource",
  "name": "my-vm",
  "type": "Microsoft.Compute/virtualMachines",
  "resource_group": "my-rg",
  "location": "canadaeast",  // Must be canadaeast or canadacentral
  "tags": {
    "environment": "production"
  },
  "searchable_text": "Azure Resource: my-vm\nType: Microsoft.Compute/virtualMachines\n..."
}
```

### Demo 2: Terraform Parsing
**Goal:** Show that we can parse Terraform files and extract resources.

**Steps:**
1. Clone a sample Terraform repository
2. Run the HCL parser
3. Show extracted resources, variables, and modules
4. Demonstrate linking to source code location

### Demo 3: Git History
**Goal:** Show that we can track infrastructure changes over time.

**Steps:**
1. Clone a repository with Terraform history
2. Extract commits that modified `.tf` files
3. Show commit metadata and affected files
4. Filter to show only infrastructure-related changes

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Azure API rate limiting | Ingestion delays | Implement exponential backoff; cache responses; use batch queries |
| Large Terraform state files | Memory issues, slow parsing | Stream processing; filter unnecessary attributes |
| Sensitive data in state | Security breach | Redact sensitive attributes; don't index secrets |
| Git repo authentication | Ingestion failure | Support multiple auth methods (PAT, SSH, managed identity) |
| Schema changes in Azure API | Parsing errors | Version pinning; graceful handling of unknown fields |
| Network connectivity | Ingestion failure | Retry logic; health checks; alerting |

---

## Open Questions

1. **State backend access:** Should we read state directly from Azure Storage, or require state to be pushed via webhook?
2. **Terraform Cloud:** Do we need to support Terraform Cloud/Enterprise API for plans and state?
3. **Private repositories:** What authentication methods are required for private Git repos?
4. **Data retention:** How long should we keep historical data? Rolling window or indefinite?
5. **Incremental updates:** For Azure resources, should we use `changedTime` for incremental sync, or always full refresh?

---

## Task List

> **See [TASKS.md](../TASKS.md)** for the authoritative task list.
>
> Tasks for this phase are under **"Phase 1: Data Ingestion"** including:
> - 1.1 Azure Infrastructure Setup
> - 1.2 Data Models
> - 1.3 Azure Resource Graph Connector
> - 1.4 Terraform HCL Connector
> - 1.5 Terraform State Connector
> - 1.6 Terraform Plan Connector
> - 1.7 Git Connector
> - 1.8 Ingestion Orchestrator

---

## Dependencies

```
# requirements.txt (Phase 1)

# Azure SDKs
azure-identity>=1.15.0
azure-mgmt-resourcegraph>=8.0.0
azure-cosmos>=4.5.0
azure-servicebus>=7.11.0
azure-storage-blob>=12.19.0
azure-keyvault-secrets>=4.7.0

# Terraform parsing
python-hcl2>=4.3.0

# Git operations
GitPython>=3.1.40

# Data modeling
pydantic>=2.5.0
pydantic-settings>=2.1.0

# Configuration
PyYAML>=6.0.1

# Async support
aiohttp>=3.9.0
asyncio>=3.4.3

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0

# Development
black>=23.0.0
ruff>=0.1.0
mypy>=1.7.0
```

---

## Milestones

### Milestone 1.1: Azure Integration (End of Week 1)
- Azure Resource Graph connector complete
- Can fetch resources from 1+ subscriptions
- Documents stored in Cosmos DB
- Basic unit and integration tests passing

### Milestone 1.2: Terraform Parsing (End of Week 2)
- HCL parser complete
- State file parser complete
- Plan parser complete
- All Terraform document types stored
- Linking between Terraform resources and Azure resources

### Milestone 1.3: Git Integration (End of Week 3)
- Git connector complete
- Commit history ingestion working
- Terraform change detection working
- Full ingestion pipeline operational
- Scheduling implemented
- Ready for Phase 2 (Indexing)
