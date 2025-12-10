# Infra-Aware RAG Assistant: Implementation Plan

## Executive Summary

This document outlines the implementation plan for an **Infra-Aware RAG (Retrieval-Augmented Generation) Assistant** — an AI-powered system that can answer questions about Azure cloud infrastructure and Terraform Infrastructure-as-Code (IaC) by ingesting and understanding:

- **Azure Resource State** via Azure Resource Graph
- **Terraform Code and Plans** from repositories
- **Git History** for change tracking and context

**CRITICAL REQUIREMENT: All Azure resources for this project MUST be deployed in Canada East (`canadaeast`) or Canada Central (`canadacentral`) regions. This is a strict requirement for data residency and compliance.**

The system enables DevOps engineers, SREs, and cloud architects to ask natural language questions like:
- "Which VMs in production don't have backup enabled?"
- "What changed in our network configuration last week?"
- "Show me all resources that would be affected by this Terraform plan"
- "Why was this storage account created and by whom?"

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interface                                 │
│                    (Chat UI / CLI / VS Code Extension)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LLM Orchestration Layer                             │
│              (Azure OpenAI / Claude + Tool Router + Memory)                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  RAG Search  │  │ Direct Query │  │  Tool APIs   │
            │   (Vector)   │  │   (Graph)    │  │  (Actions)   │
            └──────────────┘  └──────────────┘  └──────────────┘
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Unified Data Layer                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Vector Store   │  │  Graph Database │  │  Document Store             │  │
│  │  (Embeddings)   │  │  (Relationships)│  │  (Raw Artifacts)            │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Data Ingestion Pipeline                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ Azure Resource  │  │   Terraform     │  │      Git History            │  │
│  │     Graph       │  │   Parser        │  │      Collector              │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
┌───────────────┐           ┌─────────────────┐           ┌─────────────────┐
│    Azure      │           │   Terraform     │           │   Git Repos     │
│ Subscriptions │           │   State Files   │           │   (IaC Code)    │
└───────────────┘           └─────────────────┘           └─────────────────┘
```

---

## Technology Stack

**All Azure services must be deployed in Canada East or Canada Central**

| Component | Recommended Technology | Region Requirement | Alternatives |
|-----------|----------------------|-------------------|--------------|
| **Runtime** | Python 3.11+ with FastAPI | N/A | Node.js/TypeScript |
| **LLM** | Azure OpenAI (4.1) | **Canada East** | Anthropic Claude, local models |
| **Embeddings** | Azure OpenAI text-embedding-3-large | **Canada East** | Cohere, sentence-transformers |
| **Vector Store** | Azure AI Search | **Canada East or Canada Central** | Pinecone, Weaviate, Qdrant |
| **Graph Database** | Azure Cosmos DB (Gremlin API) | **Canada East or Canada Central** | Neo4j, Neptune |
| **Document Store** | Azure Cosmos DB (NoSQL) | **Canada East or Canada Central** | PostgreSQL + pgvector |
| **Cache** | Azure Redis Cache | **Canada East or Canada Central** | Local Redis |
| **Queue** | Azure Service Bus | **Canada East or Canada Central** | RabbitMQ, Azure Queue Storage |
| **Blob Storage** | Azure Blob Storage | **Canada East or Canada Central** | S3-compatible |
| **Auth** | Microsoft Entra ID (AAD) | Global (tenant-level) | Auth0, Keycloak |
| **CI/CD** | Azure DevOps / GitHub Actions | N/A | GitLab CI |
| **Infrastructure** | Terraform (dogfooding) | N/A | Bicep, Pulumi |
| **Container Runtime** | Azure Container Apps | **Canada East or Canada Central** | AKS, Azure Functions |
| **Monitoring** | Azure Monitor + App Insights | **Canada East or Canada Central** | Datadog, Grafana |

---

## Implementation Phases

### Phase 1: Data Ingestion
**Goal:** Build connectors to ingest data from Azure, Terraform, and Git sources.

See: [01-data-ingestion.md](./01-data-ingestion.md)

**Key Deliverables:**
- Azure Resource Graph connector with subscription enumeration
- Terraform HCL parser and state file processor
- Git repository cloner and commit history analyzer
- Unified data model for resources, code, and changes
- Initial data pipeline with scheduling

---

### Phase 2: Indexing and Search
**Goal:** Create embeddings, build vector indexes, and establish a graph of relationships.

See: [02-indexing-and-search.md](./02-indexing-and-search.md)

**Key Deliverables:**
- Chunking strategy for different content types
- Embedding generation pipeline
- Vector index in Azure AI Search
- Graph model in Cosmos DB (Gremlin)
- Hybrid search (vector + keyword + graph traversal)

---

### Phase 3: API and Tools
**Goal:** Build the API layer and define tools the LLM can use.

See: [03-api-and-tools.md](./03-api-and-tools.md)

**Key Deliverables:**
- RESTful API for search and retrieval
- Tool definitions for LLM function calling
- Direct Azure Resource Graph query capability
- Terraform plan analysis tools
- Authentication and authorization layer

---

### Phase 4: LLM Orchestration and UI
**Goal:** Integrate the LLM, build conversation management, and create the user interface.

See: [04-llm-orchestration-and-ui.md](./04-llm-orchestration-and-ui.md)

**Key Deliverables:**
- LLM integration with tool routing
- Conversation memory and context management
- Chat UI (web-based)
- CLI tool for terminal users
- VS Code extension (stretch goal)

---

## High-Level Data Model

### Core Entities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENTITY RELATIONSHIPS                           │
└─────────────────────────────────────────────────────────────────────────────┘

AzureResource ─────────────── manages ──────────────▶ TerraformResource
      │                                                      │
      │ contains                                             │ defined_in
      ▼                                                      ▼
AzureResource                                         TerraformFile
      │                                                      │
      │ changed_by                                           │ part_of
      ▼                                                      ▼
ResourceChange ◀────── produced_by ───────────────── GitCommit
      │                                                      │
      │ part_of                                              │ authored_by
      ▼                                                      ▼
TerraformPlan                                         GitAuthor
```

### Entity Definitions

```python
# Core entities (simplified)

class AzureResource:
    id: str                    # Azure Resource ID
    type: str                  # e.g., "Microsoft.Compute/virtualMachines"
    name: str
    resource_group: str
    subscription_id: str
    location: str
    tags: dict[str, str]
    properties: dict           # Full resource properties
    sku: dict | None
    created_time: datetime
    last_modified: datetime

class TerraformResource:
    address: str               # e.g., "azurerm_virtual_machine.main"
    type: str                  # e.g., "azurerm_virtual_machine"
    name: str
    module_path: str | None
    provider: str
    attributes: dict
    dependencies: list[str]
    source_file: str
    source_line: int

class TerraformFile:
    path: str
    repo_url: str
    branch: str
    content_hash: str
    resources: list[str]       # Resource addresses
    variables: list[str]
    outputs: list[str]
    modules: list[str]

class TerraformPlan:
    id: str
    created_at: datetime
    git_commit: str
    changes: list[ResourceChange]
    summary: PlanSummary

class ResourceChange:
    resource_address: str
    azure_resource_id: str | None
    action: Literal["create", "update", "delete", "replace", "no-op"]
    before: dict | None
    after: dict | None
    diff: list[AttributeChange]

class GitCommit:
    sha: str
    repo_url: str
    branch: str
    message: str
    author: str
    author_email: str
    timestamp: datetime
    files_changed: list[str]
    diff_summary: str
```

---

## Cross-Cutting Concerns

### Authentication & Authorization

| Concern | Approach |
|---------|----------|
| **User Auth** | Microsoft Entra ID (AAD) with OAuth2/OIDC |
| **Service Auth** | Managed Identity for Azure resources |
| **RBAC** | Map AAD groups to subscription access |
| **API Auth** | Bearer tokens (JWT) validated against AAD |
| **Audit** | Log all queries with user identity |

### Multi-Subscription Support

```yaml
# Configuration model for multi-subscription
# IMPORTANT: This project's Azure resources must be in Canada East or Canada Central
azure_region: "canadaeast"  # or "canadacentral"

subscriptions:
  - id: "sub-prod-001"
    name: "Production"
    tenant_id: "tenant-123"
    access_level: "read"

  - id: "sub-dev-001"
    name: "Development"
    tenant_id: "tenant-123"
    access_level: "read"

git_repos:
  - url: "https://github.com/org/infra-prod"
    branch: "main"
    terraform_paths: ["terraform/"]

  - url: "https://github.com/org/infra-dev"
    branch: "main"
    terraform_paths: ["infrastructure/"]
```

### Security Considerations

1. **Secrets Management:** Azure Key Vault for all credentials
2. **Network:** Private endpoints for all Azure services
3. **Data Classification:** Tag sensitive resources, filter from responses
4. **Query Sanitization:** Prevent injection in Resource Graph queries
5. **Rate Limiting:** Protect against abuse
6. **Data Retention:** Configurable retention policies

### Performance Targets

| Metric | Target (MVP) | Target (Production) |
|--------|-------------|---------------------|
| Query Latency (p50) | < 3s | < 1s |
| Query Latency (p99) | < 10s | < 5s |
| Ingestion Freshness | 15 min | 5 min |
| Concurrent Users | 10 | 100 |
| Resources Indexed | 10,000 | 1,000,000 |

### Cost Considerations

| Component | Estimated Monthly Cost (MVP) |
|-----------|------------------------------|
| Azure OpenAI (GPT-4.1) | $200-500 |
| Azure AI Search (Basic) | $75 |
| Cosmos DB (Serverless) | $50-100 |
| Container Apps | $50-100 |
| Blob Storage | $10 |
| Azure Monitor | $20 |
| **Total** | **$400-800/month** |

---

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM hallucinations about infrastructure | High | Medium | Ground responses with retrieved context; show sources |
| Azure API rate limiting | Medium | Medium | Implement backoff; cache aggressively |
| Terraform state contains secrets | High | High | Filter sensitive attributes before indexing |
| Stale data leading to wrong answers | Medium | Medium | Show data freshness; real-time option for critical queries |
| Complex queries exceed context limits | Medium | Medium | Implement summarization; chunked retrieval |
| Multi-tenant data leakage | Critical | Low | Strict RBAC; query-time filtering; audit logging |
| Cost overruns from LLM usage | Medium | Medium | Token budgets; caching; cheaper models for simple queries |

---

## Open Questions

1. **State file access:** Should we read Terraform state from remote backends directly, or require state to be pushed to us?
2. **Real-time vs. batch:** Do we need real-time streaming of Azure changes (Event Grid) for MVP?
3. **Write operations:** Should the assistant be able to generate/apply Terraform changes, or read-only for MVP?
4. **Compliance:** Are there specific compliance requirements (SOC2, HIPAA) that affect architecture?
5. **On-premises:** Any requirement to support Azure Stack or hybrid environments?

---

## Success Criteria for MVP

- [ ] Can answer "What resources exist in subscription X?" in < 5 seconds
- [ ] Can explain what a Terraform plan will change with 90%+ accuracy
- [ ] Can trace a resource back to the Terraform code that created it
- [ ] Can show git history for infrastructure changes
- [ ] Handles 3+ subscriptions and 5,000+ resources
- [ ] Passes security review for read-only production access
- [ ] Documentation sufficient for team onboarding

---

## Task Tracking

> **See [TASKS.md](../TASKS.md)** for the master task list with checkboxes.
>
> All implementation tasks are centralized there for easy tracking.

---

## Phase Documents

1. [01-data-ingestion.md](./01-data-ingestion.md) - Data collection from Azure, Terraform, and Git
2. [02-indexing-and-search.md](./02-indexing-and-search.md) - Embeddings, vector store, and graph database
3. [03-api-and-tools.md](./03-api-and-tools.md) - API layer and LLM tool definitions
4. [04-llm-orchestration-and-ui.md](./04-llm-orchestration-and-ui.md) - LLM integration and user interfaces

---

## Appendix: Example Queries

The system should be able to answer questions like:

**Resource Discovery:**
- "List all VMs in production that are running Windows Server 2016"
- "Which storage accounts don't have soft delete enabled?"
- "Show me all public IP addresses across our subscriptions"

**Change Analysis:**
- "What infrastructure changes were made last week?"
- "Who modified the network security groups recently?"
- "What will this Terraform plan change?"

**Troubleshooting:**
- "Why is this VM in a failed state?"
- "What resources depend on this virtual network?"
- "Show me the Terraform code for this load balancer"

**Compliance:**
- "Which resources are missing required tags?"
- "Are all our databases encrypted at rest?"
- "List resources that don't follow our naming convention"

**Cost:**
- "What are the most expensive resources in dev?"
- "Which VMs have been running but idle for 30+ days?"
