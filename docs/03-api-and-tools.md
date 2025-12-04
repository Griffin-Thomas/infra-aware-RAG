# Phase 3: API and Tools

## Overview

This phase builds the API layer that exposes infrastructure search and query capabilities, and defines the tools that the LLM can use for function calling. We will:

1. **Design RESTful APIs** for search, retrieval, and queries
2. **Define LLM tools** using the function calling schema
3. **Implement Azure Resource Graph** direct query capability
4. **Build Terraform plan analysis** tools
5. **Create authentication and authorization** middleware

By the end of this phase, we will have a complete API surface that can be consumed by the LLM orchestration layer and direct API clients.

---

## Scope

### In Scope
- RESTful API with OpenAPI specification
- LLM tool definitions (function calling schema)
- Hybrid search API (vector + keyword + graph)
- Azure Resource Graph passthrough queries
- Terraform plan parsing and analysis
- Resource detail retrieval
- Git history queries
- Authentication via Azure AD
- Rate limiting and usage tracking

### Out of Scope (Future Phases)
- Write operations (creating/modifying resources)
- Terraform plan execution
- Real-time subscriptions/webhooks
- GraphQL API
- Multi-region deployment

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API Gateway                                       │
│              (Azure API Management or Application Gateway)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Search     │  │   Resource   │  │  Terraform   │  │     Git      │     │
│  │   Router     │  │   Router     │  │   Router     │  │   Router     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
       ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
       │   Hybrid    │         │   Azure     │         │   Cosmos    │
       │   Search    │         │   Resource  │         │     DB      │
       │   Engine    │         │   Graph     │         │   (Docs)    │
       └─────────────┘         └─────────────┘         └─────────────┘
```

---

## Technology Decisions

### Web Framework

**Decision:** FastAPI with Python 3.11+

**Rationale:**
- Automatic OpenAPI/Swagger documentation
- Native async support for high concurrency
- Pydantic integration for request/response validation
- Type hints for better developer experience
- High performance (Starlette + Uvicorn)

**Alternatives Considered:**
- Flask: Simpler but no native async, manual OpenAPI
- Django: Too heavy for API-only service
- Node.js/Express: Good but team prefers Python

### Authentication

**Decision:** Azure AD (Entra ID) with OAuth2/OIDC

**Rationale:**
- Native Azure integration
- Managed Identity support for services
- Group-based RBAC
- Industry standard (OAuth2)

### Hosting

**Decision:** Azure Container Apps

**Rationale:**
- Serverless containers with scale-to-zero
- Built-in ingress and TLS
- Managed Identity support
- Lower operational overhead than AKS

---

## API Design

### Base URL and Versioning

```
https://infra-rag.{environment}.azure.example.com/api/v1
```

### OpenAPI Specification

```yaml
openapi: 3.1.0
info:
  title: Infra-Aware RAG API
  description: API for querying Azure infrastructure and Terraform IaC
  version: 1.0.0

servers:
  - url: https://infra-rag.prod.azure.example.com/api/v1
    description: Production
  - url: https://infra-rag.dev.azure.example.com/api/v1
    description: Development

security:
  - bearerAuth: []

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    SearchRequest:
      type: object
      required:
        - query
      properties:
        query:
          type: string
          description: Natural language search query
          example: "virtual machines in production without backup"
        mode:
          type: string
          enum: [vector, keyword, hybrid]
          default: hybrid
        doc_types:
          type: array
          items:
            type: string
            enum: [azure_resource, terraform_resource, git_commit, terraform_plan]
        filters:
          type: object
          additionalProperties: true
        top:
          type: integer
          minimum: 1
          maximum: 100
          default: 10

    SearchResponse:
      type: object
      properties:
        results:
          type: array
          items:
            $ref: '#/components/schemas/SearchResult'
        total_count:
          type: integer
        facets:
          type: object

    SearchResult:
      type: object
      properties:
        id:
          type: string
        score:
          type: number
        content:
          type: string
        doc_type:
          type: string
        metadata:
          type: object
        highlights:
          type: array
          items:
            type: string

    AzureResource:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        type:
          type: string
        resourceGroup:
          type: string
        subscriptionId:
          type: string
        location:
          type: string
        tags:
          type: object
        properties:
          type: object

    TerraformResource:
      type: object
      properties:
        address:
          type: string
        type:
          type: string
        name:
          type: string
        filePath:
          type: string
        repoUrl:
          type: string
        sourceCode:
          type: string

    TerraformPlanSummary:
      type: object
      properties:
        planId:
          type: string
        add:
          type: integer
        change:
          type: integer
        destroy:
          type: integer
        changes:
          type: array
          items:
            $ref: '#/components/schemas/PlannedChange'

    PlannedChange:
      type: object
      properties:
        address:
          type: string
        action:
          type: string
          enum: [create, update, delete, replace, no-op]
        resourceType:
          type: string
        changedAttributes:
          type: array
          items:
            type: string
```

### API Endpoints

```yaml
paths:
  /search:
    post:
      summary: Search infrastructure
      description: Search across Azure resources, Terraform code, and Git history
      operationId: search
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SearchRequest'
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SearchResponse'

  /resources/{resource_id}:
    get:
      summary: Get resource details
      description: Get full details for an Azure resource
      operationId: getResource
      parameters:
        - name: resource_id
          in: path
          required: true
          schema:
            type: string
          description: Azure Resource ID (URL encoded)
      responses:
        '200':
          description: Resource details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AzureResource'

  /resources/{resource_id}/terraform:
    get:
      summary: Get Terraform for resource
      description: Find Terraform code that manages this resource
      operationId: getTerraformForResource
      parameters:
        - name: resource_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Terraform resources
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/TerraformResource'

  /resources/{resource_id}/dependencies:
    get:
      summary: Get resource dependencies
      description: Get resources that this resource depends on or that depend on it
      operationId: getResourceDependencies
      parameters:
        - name: resource_id
          in: path
          required: true
          schema:
            type: string
        - name: direction
          in: query
          schema:
            type: string
            enum: [in, out, both]
            default: both
        - name: depth
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 5
            default: 2
      responses:
        '200':
          description: Related resources

  /resource-graph/query:
    post:
      summary: Execute Resource Graph query
      description: Execute a raw Azure Resource Graph query
      operationId: resourceGraphQuery
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - query
              properties:
                query:
                  type: string
                  description: Kusto query
                subscriptions:
                  type: array
                  items:
                    type: string
      responses:
        '200':
          description: Query results

  /terraform/resources:
    get:
      summary: List Terraform resources
      description: List Terraform resources with optional filters
      operationId: listTerraformResources
      parameters:
        - name: repo_url
          in: query
          schema:
            type: string
        - name: type
          in: query
          schema:
            type: string
        - name: file_path
          in: query
          schema:
            type: string
      responses:
        '200':
          description: Terraform resources

  /terraform/plans:
    get:
      summary: List Terraform plans
      description: List recent Terraform plans
      operationId: listTerraformPlans
      parameters:
        - name: repo_url
          in: query
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 10
      responses:
        '200':
          description: Terraform plans

  /terraform/plans/{plan_id}:
    get:
      summary: Get Terraform plan details
      description: Get full details for a Terraform plan
      operationId: getTerraformPlan
      parameters:
        - name: plan_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Plan details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TerraformPlanSummary'

  /terraform/plans/{plan_id}/analyze:
    post:
      summary: Analyze Terraform plan
      description: Get AI-generated analysis of what a plan will change
      operationId: analyzeTerraformPlan
      parameters:
        - name: plan_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Plan analysis

  /git/commits:
    get:
      summary: List Git commits
      description: List recent commits with optional filters
      operationId: listGitCommits
      parameters:
        - name: repo_url
          in: query
          schema:
            type: string
        - name: author
          in: query
          schema:
            type: string
        - name: since
          in: query
          schema:
            type: string
            format: date-time
        - name: terraform_only
          in: query
          schema:
            type: boolean
            default: false
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
      responses:
        '200':
          description: Git commits

  /git/commits/{sha}:
    get:
      summary: Get commit details
      description: Get full details for a Git commit
      operationId: getGitCommit
      parameters:
        - name: sha
          in: path
          required: true
          schema:
            type: string
        - name: repo_url
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Commit details
```

---

## FastAPI Implementation

### Application Structure

```
src/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── dependencies.py      # Shared dependencies
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication
│   │   ├── rate_limit.py    # Rate limiting
│   │   └── logging.py       # Request logging
│   └── routers/
│       ├── __init__.py
│       ├── search.py        # Search endpoints
│       ├── resources.py     # Resource endpoints
│       ├── terraform.py     # Terraform endpoints
│       ├── git.py           # Git endpoints
│       └── tools.py         # LLM tool endpoints
├── services/
│   ├── __init__.py
│   ├── search_service.py
│   ├── resource_service.py
│   ├── terraform_service.py
│   └── git_service.py
└── models/
    ├── __init__.py
    ├── requests.py
    └── responses.py
```

### Main Application

```python
# src/api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .routers import search, resources, terraform, git, tools
from .middleware.auth import AuthMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.logging import LoggingMiddleware
from .dependencies import get_settings, init_services, cleanup_services

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    await init_services(settings)
    yield
    # Shutdown
    await cleanup_services()

app = FastAPI(
    title="Infra-Aware RAG API",
    description="API for querying Azure infrastructure and Terraform IaC",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)

# Routers
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(resources.router, prefix="/api/v1", tags=["resources"])
app.include_router(terraform.router, prefix="/api/v1", tags=["terraform"])
app.include_router(git.router, prefix="/api/v1", tags=["git"])
app.include_router(tools.router, prefix="/api/v1", tags=["tools"])

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    # Check dependencies
    return {"status": "ready"}
```

### Search Router

```python
# src/api/routers/search.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from ..dependencies import get_search_engine
from ...search.hybrid_search import HybridSearchEngine, HybridSearchResults

router = APIRouter()

class SearchRequest(BaseModel):
    """Search request model."""
    query: str = Field(..., min_length=1, max_length=1000)
    mode: str = Field(default="hybrid", pattern="^(vector|keyword|hybrid)$")
    doc_types: list[str] | None = None
    filters: dict[str, Any] | None = None
    top: int = Field(default=10, ge=1, le=100)
    include_facets: bool = False

class SearchResult(BaseModel):
    """Individual search result."""
    id: str
    score: float
    content: str
    doc_type: str
    metadata: dict[str, Any]
    highlights: list[str] | None = None

class SearchResponse(BaseModel):
    """Search response model."""
    results: list[SearchResult]
    total_count: int
    facets: dict[str, Any] | None = None

@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_engine: HybridSearchEngine = Depends(get_search_engine),
):
    """
    Search across infrastructure data.

    Supports multiple search modes:
    - **vector**: Semantic similarity search using embeddings
    - **keyword**: Traditional full-text search with semantic ranking
    - **hybrid**: Combined vector and keyword search (recommended)

    Filter by document types:
    - `azure_resource`: Azure resources from Resource Graph
    - `terraform_resource`: Terraform resource definitions
    - `git_commit`: Git commit history
    - `terraform_plan`: Terraform plan analysis

    Additional filters can be applied using the `filters` parameter.
    """
    try:
        results = await search_engine.search(
            query=request.query,
            mode=request.mode,
            doc_types=request.doc_types,
            filters=request.filters,
            top=request.top,
            include_facets=request.include_facets,
        )

        return SearchResponse(
            results=[
                SearchResult(
                    id=r.id,
                    score=r.score,
                    content=r.content,
                    doc_type=r.doc_type,
                    metadata=r.metadata,
                    highlights=r.highlights,
                )
                for r in results.results
            ],
            total_count=results.total_count,
            facets=results.facets,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/expand", response_model=SearchResponse)
async def search_with_expansion(
    request: SearchRequest,
    expand_depth: int = Field(default=1, ge=1, le=3),
    search_engine: HybridSearchEngine = Depends(get_search_engine),
):
    """
    Search with graph expansion.

    First performs a hybrid search, then expands results using
    the graph database to find related resources.
    """
    results = await search_engine.search_with_graph_expansion(
        query=request.query,
        top=request.top,
        expand_depth=expand_depth,
    )

    return SearchResponse(
        results=[
            SearchResult(
                id=r.id,
                score=r.score,
                content=r.content,
                doc_type=r.doc_type,
                metadata=r.metadata,
                highlights=r.highlights,
            )
            for r in results.results
        ],
        total_count=results.total_count,
    )
```

### Resources Router

```python
# src/api/routers/resources.py

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Any
from urllib.parse import unquote

from ..dependencies import get_resource_service, get_graph_builder

router = APIRouter()

class AzureResource(BaseModel):
    """Azure resource model."""
    id: str
    name: str
    type: str
    resource_group: str
    subscription_id: str
    subscription_name: str
    location: str
    tags: dict[str, str]
    sku: dict[str, Any] | None = None
    kind: str | None = None
    properties: dict[str, Any]

class TerraformLink(BaseModel):
    """Terraform resource link."""
    address: str
    type: str
    file_path: str
    line_number: int
    repo_url: str
    branch: str
    source_code: str

class ResourceDependency(BaseModel):
    """Resource dependency."""
    id: str
    name: str
    type: str
    relationship: str
    direction: str  # "upstream" or "downstream"

@router.get("/resources/{resource_id:path}", response_model=AzureResource)
async def get_resource(
    resource_id: str,
    resource_service = Depends(get_resource_service),
):
    """
    Get full details for an Azure resource.

    The resource_id should be the full Azure Resource ID, URL encoded.
    Example: `/subscriptions/xxx/resourceGroups/yyy/providers/Microsoft.Compute/virtualMachines/zzz`
    """
    decoded_id = unquote(resource_id)
    resource = await resource_service.get_resource(decoded_id)

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    return resource


@router.get("/resources/{resource_id:path}/terraform", response_model=list[TerraformLink])
async def get_terraform_for_resource(
    resource_id: str,
    resource_service = Depends(get_resource_service),
    graph_builder = Depends(get_graph_builder),
):
    """
    Find Terraform code that manages this resource.

    Returns all Terraform resources that are linked to this Azure resource,
    including the source code location.
    """
    decoded_id = unquote(resource_id)

    terraform_links = graph_builder.find_terraform_for_resource(decoded_id)

    result = []
    for link in terraform_links:
        tf_resource = await resource_service.get_terraform_resource(link["address"])
        if tf_resource:
            result.append(TerraformLink(
                address=tf_resource.address,
                type=tf_resource.type,
                file_path=tf_resource.file_path,
                line_number=tf_resource.line_number,
                repo_url=tf_resource.repo_url,
                branch=tf_resource.branch,
                source_code=tf_resource.source_code,
            ))

    return result


@router.get("/resources/{resource_id:path}/dependencies", response_model=list[ResourceDependency])
async def get_resource_dependencies(
    resource_id: str,
    direction: str = Query(default="both", pattern="^(in|out|both)$"),
    depth: int = Query(default=2, ge=1, le=5),
    graph_builder = Depends(get_graph_builder),
):
    """
    Get resources related to this resource.

    - **in**: Resources that depend on this resource
    - **out**: Resources that this resource depends on
    - **both**: All related resources
    """
    decoded_id = unquote(resource_id)

    dependencies = graph_builder.find_dependencies(decoded_id, direction, depth)

    result = []
    for dep in dependencies:
        result.append(ResourceDependency(
            id=dep["id"],
            name=dep["name"],
            type=dep["type"],
            relationship=dep.get("relationship", "related"),
            direction="upstream" if dep.get("direction") == "in" else "downstream",
        ))

    return result


@router.post("/resource-graph/query")
async def resource_graph_query(
    request: dict,
    resource_service = Depends(get_resource_service),
):
    """
    Execute a raw Azure Resource Graph query.

    The query should be a valid Kusto query. Results are returned as-is
    from the Resource Graph API.

    Example query:
    ```
    Resources
    | where type == 'microsoft.compute/virtualmachines'
    | project name, resourceGroup, location
    ```
    """
    query = request.get("query")
    subscriptions = request.get("subscriptions")

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    # Validate query (basic check)
    if ";" in query or "--" in query:
        raise HTTPException(status_code=400, detail="Invalid query")

    results = await resource_service.execute_resource_graph_query(
        query=query,
        subscriptions=subscriptions,
    )

    return {"results": results}
```

### Terraform Router

```python
# src/api/routers/terraform.py

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Any
from datetime import datetime

from ..dependencies import get_terraform_service

router = APIRouter()

class TerraformResource(BaseModel):
    """Terraform resource model."""
    address: str
    type: str
    name: str
    module_path: str | None
    file_path: str
    line_number: int
    repo_url: str
    branch: str
    provider: str
    source_code: str
    dependencies: list[str]
    azure_resource_id: str | None

class PlannedChange(BaseModel):
    """A planned resource change."""
    address: str
    action: str
    resource_type: str
    changed_attributes: list[str]
    summary: str

class TerraformPlan(BaseModel):
    """Terraform plan model."""
    id: str
    repo_url: str
    branch: str
    commit_sha: str
    timestamp: datetime
    add: int
    change: int
    destroy: int
    changes: list[PlannedChange]

class PlanAnalysis(BaseModel):
    """AI-generated plan analysis."""
    summary: str
    risk_level: str  # low, medium, high
    key_changes: list[str]
    recommendations: list[str]

@router.get("/terraform/resources", response_model=list[TerraformResource])
async def list_terraform_resources(
    repo_url: str | None = None,
    type: str | None = None,
    file_path: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    terraform_service = Depends(get_terraform_service),
):
    """
    List Terraform resources with optional filters.
    """
    resources = await terraform_service.list_resources(
        repo_url=repo_url,
        resource_type=type,
        file_path=file_path,
        limit=limit,
    )

    return resources


@router.get("/terraform/resources/{address:path}", response_model=TerraformResource)
async def get_terraform_resource(
    address: str,
    repo_url: str = Query(...),
    terraform_service = Depends(get_terraform_service),
):
    """
    Get a specific Terraform resource by address.
    """
    resource = await terraform_service.get_resource(address, repo_url)

    if not resource:
        raise HTTPException(status_code=404, detail="Terraform resource not found")

    return resource


@router.get("/terraform/plans", response_model=list[TerraformPlan])
async def list_terraform_plans(
    repo_url: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    terraform_service = Depends(get_terraform_service),
):
    """
    List recent Terraform plans.
    """
    plans = await terraform_service.list_plans(
        repo_url=repo_url,
        since=since,
        limit=limit,
    )

    return plans


@router.get("/terraform/plans/{plan_id}", response_model=TerraformPlan)
async def get_terraform_plan(
    plan_id: str,
    terraform_service = Depends(get_terraform_service),
):
    """
    Get full details for a Terraform plan.
    """
    plan = await terraform_service.get_plan(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    return plan


@router.post("/terraform/plans/{plan_id}/analyze", response_model=PlanAnalysis)
async def analyze_terraform_plan(
    plan_id: str,
    terraform_service = Depends(get_terraform_service),
):
    """
    Get AI-generated analysis of a Terraform plan.

    Returns a summary of what will change, risk assessment,
    and recommendations.
    """
    plan = await terraform_service.get_plan(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    analysis = await terraform_service.analyze_plan(plan)

    return analysis


@router.post("/terraform/plans/parse")
async def parse_terraform_plan(
    plan_json: dict,
    terraform_service = Depends(get_terraform_service),
):
    """
    Parse a Terraform plan JSON and return structured changes.

    Accepts the output of `terraform plan -json` or `terraform show -json`.
    """
    try:
        parsed = terraform_service.parse_plan(plan_json)
        return parsed
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse plan: {e}")
```

### Git Router

```python
# src/api/routers/git.py

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

from ..dependencies import get_git_service

router = APIRouter()

class FileChange(BaseModel):
    """File change in a commit."""
    path: str
    change_type: str
    additions: int
    deletions: int

class GitCommit(BaseModel):
    """Git commit model."""
    sha: str
    short_sha: str
    repo_url: str
    branch: str
    message: str
    author_name: str
    author_email: str
    commit_date: datetime
    files_changed: list[FileChange]
    terraform_files: list[str]
    has_terraform_changes: bool

@router.get("/git/commits", response_model=list[GitCommit])
async def list_git_commits(
    repo_url: str | None = None,
    author: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    terraform_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    git_service = Depends(get_git_service),
):
    """
    List Git commits with optional filters.

    Filter options:
    - **repo_url**: Filter by repository
    - **author**: Filter by author name or email
    - **since/until**: Date range filter
    - **terraform_only**: Only show commits with Terraform changes
    """
    commits = await git_service.list_commits(
        repo_url=repo_url,
        author=author,
        since=since,
        until=until,
        terraform_only=terraform_only,
        limit=limit,
    )

    return commits


@router.get("/git/commits/{sha}", response_model=GitCommit)
async def get_git_commit(
    sha: str,
    repo_url: str = Query(...),
    git_service = Depends(get_git_service),
):
    """
    Get full details for a Git commit.
    """
    commit = await git_service.get_commit(sha, repo_url)

    if not commit:
        raise HTTPException(status_code=404, detail="Commit not found")

    return commit


@router.get("/git/commits/{sha}/diff")
async def get_commit_diff(
    sha: str,
    repo_url: str = Query(...),
    file_path: str | None = None,
    git_service = Depends(get_git_service),
):
    """
    Get the diff for a commit.

    Optionally filter to a specific file path.
    """
    diff = await git_service.get_diff(sha, repo_url, file_path)

    if diff is None:
        raise HTTPException(status_code=404, detail="Commit not found")

    return {"diff": diff}
```

---

## LLM Tool Definitions

Tools are defined using a schema compatible with OpenAI/Anthropic function calling.

```python
# src/api/tools/definitions.py

from typing import Any

TOOL_DEFINITIONS = [
    {
        "name": "search_infrastructure",
        "description": """Search across Azure resources, Terraform code, and Git history.
        Use this tool to find resources by name, type, tags, or any other attribute.
        Returns relevant results with metadata and relevance scores.""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query"
                },
                "doc_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific document types: azure_resource, terraform_resource, git_commit, terraform_plan"
                },
                "filters": {
                    "type": "object",
                    "description": "Additional filters (e.g., location, resource_group, subscription_id)"
                },
                "top": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_resource_details",
        "description": """Get full details for a specific Azure resource by its ID.
        Use this when you need complete information about a single resource.""",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "The full Azure Resource ID"
                }
            },
            "required": ["resource_id"]
        }
    },
    {
        "name": "get_resource_terraform",
        "description": """Find the Terraform code that manages an Azure resource.
        Returns the Terraform resource definition including file path and source code.""",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "The Azure Resource ID to find Terraform for"
                }
            },
            "required": ["resource_id"]
        }
    },
    {
        "name": "get_resource_dependencies",
        "description": """Get resources that depend on or are depended upon by a given resource.
        Useful for understanding impact of changes.""",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "The Azure Resource ID"
                },
                "direction": {
                    "type": "string",
                    "enum": ["in", "out", "both"],
                    "description": "Direction of dependencies (default: both)"
                },
                "depth": {
                    "type": "integer",
                    "description": "How many levels of dependencies to traverse (default: 2)"
                }
            },
            "required": ["resource_id"]
        }
    },
    {
        "name": "query_resource_graph",
        "description": """Execute a Kusto query against Azure Resource Graph.
        Use this for complex queries that need filtering, aggregation, or joins.
        The query language is Kusto (KQL).""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Kusto query to execute against Resource Graph"
                },
                "subscriptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of subscription IDs to query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_terraform_plan",
        "description": """Get details of a Terraform plan including all planned changes.
        Use this to understand what will happen when a plan is applied.""",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "The plan ID"
                }
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "analyze_terraform_plan",
        "description": """Get AI-generated analysis of a Terraform plan.
        Returns a summary, risk assessment, and recommendations.""",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "The plan ID to analyze"
                }
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "get_git_history",
        "description": """Get Git commit history for infrastructure changes.
        Use this to understand who changed what and when.""",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_url": {
                    "type": "string",
                    "description": "Repository URL (optional)"
                },
                "author": {
                    "type": "string",
                    "description": "Filter by author name or email"
                },
                "since": {
                    "type": "string",
                    "description": "Start date (ISO format)"
                },
                "terraform_only": {
                    "type": "boolean",
                    "description": "Only show commits with Terraform changes"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of commits to return (default: 20)"
                }
            }
        }
    },
    {
        "name": "get_commit_details",
        "description": """Get full details for a specific Git commit including diff.""",
        "parameters": {
            "type": "object",
            "properties": {
                "sha": {
                    "type": "string",
                    "description": "The commit SHA"
                },
                "repo_url": {
                    "type": "string",
                    "description": "Repository URL"
                }
            },
            "required": ["sha", "repo_url"]
        }
    },
    {
        "name": "list_subscriptions",
        "description": """List all Azure subscriptions that are being tracked.
        Returns subscription IDs and names.""",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_resource_types_summary",
        "description": """Get a summary of all resource types and their counts.
        Useful for understanding what's in the environment.""",
        "parameters": {
            "type": "object",
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "Optional subscription ID to filter"
                }
            }
        }
    }
]


def get_tool_definitions() -> list[dict]:
    """Get all tool definitions."""
    return TOOL_DEFINITIONS


def get_tool_by_name(name: str) -> dict | None:
    """Get a specific tool definition by name."""
    for tool in TOOL_DEFINITIONS:
        if tool["name"] == name:
            return tool
    return None
```

### Tool Router (for LLM)

```python
# src/api/routers/tools.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from ..dependencies import (
    get_search_engine,
    get_resource_service,
    get_terraform_service,
    get_git_service,
)
from .definitions import TOOL_DEFINITIONS

router = APIRouter()

class ToolCallRequest(BaseModel):
    """Request to execute a tool."""
    name: str
    arguments: dict[str, Any]

class ToolCallResponse(BaseModel):
    """Response from tool execution."""
    name: str
    result: Any
    error: str | None = None

@router.get("/tools")
async def list_tools():
    """
    List all available tools with their definitions.

    Returns tool definitions in function calling schema format.
    """
    return {"tools": TOOL_DEFINITIONS}


@router.post("/tools/execute", response_model=ToolCallResponse)
async def execute_tool(
    request: ToolCallRequest,
    search_engine = Depends(get_search_engine),
    resource_service = Depends(get_resource_service),
    terraform_service = Depends(get_terraform_service),
    git_service = Depends(get_git_service),
):
    """
    Execute a tool by name with given arguments.

    This endpoint is used by the LLM orchestration layer to execute
    function calls.
    """
    try:
        result = await _execute_tool(
            name=request.name,
            arguments=request.arguments,
            search_engine=search_engine,
            resource_service=resource_service,
            terraform_service=terraform_service,
            git_service=git_service,
        )
        return ToolCallResponse(name=request.name, result=result)

    except ValueError as e:
        return ToolCallResponse(name=request.name, result=None, error=str(e))
    except Exception as e:
        return ToolCallResponse(name=request.name, result=None, error=f"Tool execution failed: {e}")


async def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    search_engine,
    resource_service,
    terraform_service,
    git_service,
) -> Any:
    """Execute a tool and return results."""

    if name == "search_infrastructure":
        results = await search_engine.search(
            query=arguments["query"],
            mode="hybrid",
            doc_types=arguments.get("doc_types"),
            filters=arguments.get("filters"),
            top=arguments.get("top", 10),
        )
        return {
            "results": [
                {
                    "id": r.id,
                    "content": r.content[:500],  # Truncate for LLM context
                    "doc_type": r.doc_type,
                    "score": r.score,
                    "metadata": r.metadata,
                }
                for r in results.results
            ],
            "total_count": results.total_count,
        }

    elif name == "get_resource_details":
        resource = await resource_service.get_resource(arguments["resource_id"])
        if not resource:
            raise ValueError("Resource not found")
        return resource.model_dump()

    elif name == "get_resource_terraform":
        terraform = await resource_service.get_terraform_for_resource(
            arguments["resource_id"]
        )
        return [t.model_dump() for t in terraform]

    elif name == "get_resource_dependencies":
        deps = await resource_service.get_dependencies(
            arguments["resource_id"],
            direction=arguments.get("direction", "both"),
            depth=arguments.get("depth", 2),
        )
        return [d.model_dump() for d in deps]

    elif name == "query_resource_graph":
        results = await resource_service.execute_resource_graph_query(
            query=arguments["query"],
            subscriptions=arguments.get("subscriptions"),
        )
        return {"results": results}

    elif name == "get_terraform_plan":
        plan = await terraform_service.get_plan(arguments["plan_id"])
        if not plan:
            raise ValueError("Plan not found")
        return plan.model_dump()

    elif name == "analyze_terraform_plan":
        plan = await terraform_service.get_plan(arguments["plan_id"])
        if not plan:
            raise ValueError("Plan not found")
        analysis = await terraform_service.analyze_plan(plan)
        return analysis.model_dump()

    elif name == "get_git_history":
        commits = await git_service.list_commits(
            repo_url=arguments.get("repo_url"),
            author=arguments.get("author"),
            since=arguments.get("since"),
            terraform_only=arguments.get("terraform_only", False),
            limit=arguments.get("limit", 20),
        )
        return [c.model_dump() for c in commits]

    elif name == "get_commit_details":
        commit = await git_service.get_commit(
            arguments["sha"],
            arguments["repo_url"],
        )
        if not commit:
            raise ValueError("Commit not found")
        return commit.model_dump()

    elif name == "list_subscriptions":
        subs = await resource_service.list_subscriptions()
        return {"subscriptions": subs}

    elif name == "get_resource_types_summary":
        summary = await resource_service.get_resource_types_summary(
            subscription_id=arguments.get("subscription_id")
        )
        return {"resource_types": summary}

    else:
        raise ValueError(f"Unknown tool: {name}")
```

---

## Authentication Middleware

```python
# src/api/middleware/auth.py

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
import httpx

class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate requests using Azure AD tokens."""

    EXEMPT_PATHS = ["/health", "/ready", "/docs", "/openapi.json"]

    def __init__(self, app, tenant_id: str, client_id: str):
        super().__init__(app)
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        self._jwks = None

    async def dispatch(self, request: Request, call_next):
        # Skip auth for exempt paths
        if any(request.url.path.startswith(p) for p in self.EXEMPT_PATHS):
            return await call_next(request)

        # Get token from header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authorization header")

        token = auth_header.split(" ")[1]

        try:
            # Validate token
            payload = await self._validate_token(token)

            # Add user info to request state
            request.state.user = {
                "sub": payload.get("sub"),
                "name": payload.get("name"),
                "email": payload.get("preferred_username"),
                "groups": payload.get("groups", []),
            }

        except JWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

        return await call_next(request)

    async def _validate_token(self, token: str) -> dict:
        """Validate JWT token against Azure AD."""
        # Get JWKS (cache this in production)
        if not self._jwks:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.jwks_url)
                self._jwks = response.json()

        # Decode and validate
        payload = jwt.decode(
            token,
            self._jwks,
            algorithms=["RS256"],
            audience=self.client_id,
            issuer=f"https://login.microsoftonline.com/{self.tenant_id}/v2.0",
        )

        return payload
```

---

## Rate Limiting

```python
# src/api/middleware/rate_limit.py

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
import asyncio

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using sliding window."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._requests: dict[str, list[datetime]] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        # Get client identifier (user ID or IP)
        client_id = self._get_client_id(request)

        # Check rate limits
        async with self._lock:
            now = datetime.utcnow()
            if client_id not in self._requests:
                self._requests[client_id] = []

            # Clean old requests
            minute_ago = now - timedelta(minutes=1)
            hour_ago = now - timedelta(hours=1)
            self._requests[client_id] = [
                r for r in self._requests[client_id]
                if r > hour_ago
            ]

            # Count recent requests
            minute_count = sum(1 for r in self._requests[client_id] if r > minute_ago)
            hour_count = len(self._requests[client_id])

            if minute_count >= self.requests_per_minute:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded (per minute)",
                    headers={"Retry-After": "60"},
                )

            if hour_count >= self.requests_per_hour:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded (per hour)",
                    headers={"Retry-After": "3600"},
                )

            # Record this request
            self._requests[client_id].append(now)

        return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Prefer user ID from auth
        if hasattr(request.state, "user") and request.state.user:
            return request.state.user.get("sub", request.client.host)
        return request.client.host
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_api_routes.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_search_engine():
    mock = AsyncMock()
    mock.search.return_value = MagicMock(
        results=[
            MagicMock(
                id="test-1",
                score=0.95,
                content="Test content",
                doc_type="azure_resource",
                metadata={},
                highlights=None,
            )
        ],
        total_count=1,
        facets=None,
    )
    return mock

class TestSearchAPI:

    def test_search_basic(self, client, mock_search_engine, monkeypatch):
        """Test basic search endpoint."""
        monkeypatch.setattr("src.api.dependencies.get_search_engine", lambda: mock_search_engine)

        response = client.post(
            "/api/v1/search",
            json={"query": "virtual machines"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "test-1"

    def test_search_with_filters(self, client, mock_search_engine, monkeypatch):
        """Test search with filters."""
        monkeypatch.setattr("src.api.dependencies.get_search_engine", lambda: mock_search_engine)

        response = client.post(
            "/api/v1/search",
            json={
                "query": "storage accounts",
                "doc_types": ["azure_resource"],
                "filters": {"location": "canadaeast"},
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        mock_search_engine.search.assert_called_once()
```

### Integration Tests

```python
# tests/integration/test_api_integration.py

import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_search_flow(api_base_url, auth_token):
    """Test complete search flow against live API."""
    async with AsyncClient(base_url=api_base_url) as client:
        # Search
        response = await client.post(
            "/api/v1/search",
            json={"query": "virtual machines in production"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data

        # Get details for first result
        if data["results"]:
            resource_id = data["results"][0]["metadata"].get("resource_id")
            if resource_id:
                detail_response = await client.get(
                    f"/api/v1/resources/{resource_id}",
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
                assert detail_response.status_code == 200
```

---

## Demo Strategy

### Demo 1: Search API
**Goal:** Show the search API finding relevant infrastructure.

**Steps:**
1. Call `/api/v1/search` with query "production databases"
2. Show returned results with scores and metadata
3. Demonstrate filtering by doc_type and location
4. Show facets for aggregation

### Demo 2: Resource Graph Query
**Goal:** Show direct Resource Graph queries.

**Steps:**
1. Call `/api/v1/resource-graph/query` with KQL query
2. Show raw results from Azure
3. Demonstrate aggregation query (count by type)
4. Show results in table format

### Demo 3: Tool Execution
**Goal:** Show the LLM tool execution flow.

**Steps:**
1. Call `/api/v1/tools` to list available tools
2. Execute `search_infrastructure` tool
3. Execute `get_resource_terraform` to find IaC
4. Execute `get_resource_dependencies` to show graph

### Demo 4: End-to-End Flow
**Goal:** Show complete query from search to Terraform.

**Steps:**
1. Search for a VM
2. Get VM details
3. Find Terraform code for VM
4. Show Git history for Terraform file

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API abuse | Service degradation | Rate limiting, authentication required |
| Resource Graph query injection | Data leakage | Query validation, parameterization |
| Token expiry handling | User experience | Token refresh flow, clear error messages |
| Large result sets | Memory/latency issues | Pagination, result limits |
| Sensitive data exposure | Security breach | Filter sensitive attributes, RBAC |
| API versioning | Breaking changes | Version prefix, deprecation policy |

---

## Open Questions

1. **API versioning:** How do we handle breaking changes? Header vs URL versioning?
2. **Pagination:** Cursor-based or offset-based pagination?
3. **Caching:** Should we cache search results? How long?
4. **Write operations:** Do we need APIs for triggering Terraform applies?
5. **WebSocket:** Do we need real-time updates via WebSocket?

---

## Task List

> **See [TASKS.md](../TASKS.md)** for the authoritative task list.
>
> Tasks for this phase are under **"Phase 3: API & Tools"** including:
> - 3.1 API Framework Setup
> - 3.2 Authentication & Authorization
> - 3.3 Rate Limiting & Logging
> - 3.4 Search Router
> - 3.5 Resources Router
> - 3.6 Terraform Router
> - 3.7 Git Router
> - 3.8 LLM Tool Definitions
> - 3.9 Tools Router

---

## Dependencies

```
# requirements.txt (Phase 3 additions)

# Web framework
fastapi>=0.109.0
uvicorn[standard]>=0.25.0
starlette>=0.35.0

# Request validation
pydantic>=2.5.0
pydantic-settings>=2.1.0

# Authentication
python-jose[cryptography]>=3.3.0
httpx>=0.26.0

# Rate limiting
limits>=3.7.0

# OpenAPI
openapi-spec-validator>=0.7.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.23.0
httpx>=0.26.0
```

---

## Milestones

### Milestone 3.1: Core API (End of Week 7)
- FastAPI application deployed
- Authentication working
- Search endpoints operational
- Rate limiting implemented

### Milestone 3.2: Full API Surface (End of Week 8)
- All resource endpoints working
- All Terraform endpoints working
- All Git endpoints working
- API documentation complete

### Milestone 3.3: LLM Tools (End of Week 9)
- Tool definitions complete
- Tool execution endpoint working
- All tools tested
- Ready for Phase 4 (LLM Orchestration)
