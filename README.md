# Infra-Aware RAG

An AI-powered assistant that answers questions about your Azure cloud infrastructure and Terraform IaC by understanding your live resource state, infrastructure code, and change history.

## What It Does

Ask natural language questions like:
- "Which VMs in production don't have backup enabled?"
- "What changed in our network configuration last week?"
- "Show me the Terraform code for this load balancer"
- "What will this Terraform plan change?"

## Data Sources

- **Azure Resource Graph** - Live state of all Azure resources
- **Terraform** - HCL code, state files, and plan analysis
- **Git History** - Who changed what and when

## Tech Stack

All Azure services deployed in **Canada East** or **Canada Central**:

- **Backend**: Python 3.11+, FastAPI
- **LLM**: Azure OpenAI (GPT-4o) - Canada East only
- **Search**: Azure AI Search (vector + keyword)
- **Graph**: Cosmos DB Gremlin API
- **Frontend**: React + TypeScript
- **CLI**: Typer + Rich

## Repository Structure

```
/
├── CLAUDE.md           # Instructions for AI agents working on this project
├── TASKS.md            # ⭐ MASTER TASK LIST - current progress tracker
├── README.md           # Project overview
├── requirements.txt    # Python dependencies
├── pyproject.toml      # Project configuration
├── .venv/              # Virtual environment
│
├── docs/               # Architecture & design documentation
│   ├── PLAN.md         # Architecture overview & decisions
│   ├── 01-data-ingestion.md
│   ├── 02-indexing-and-search.md
│   ├── 03-api-and-tools.md
│   ├── 04-llm-orchestration-and-ui.md
│   └── schemas/        # Exported JSON schemas
│
├── src/                # Production code
│   ├── models/         # Data models (Pydantic)
│   │   ├── documents.py       # Document models for all data types
│   │   └── schema_export.py   # JSON schema export utilities
│   │
│   ├── ingestion/      # Phase 1: Data collection
│   │   ├── connectors/        # Data source connectors
│   │   │   ├── azure_resource_graph.py
│   │   │   ├── terraform_hcl.py
│   │   │   ├── terraform_state.py
│   │   │   ├── terraform_plan.py
│   │   │   └── git_connector.py
│   │   ├── models.py          # Ingestion job models
│   │   └── orchestrator.py    # Job scheduling & coordination
│   │
│   ├── indexing/       # Phase 2: Embeddings & indexing
│   │   ├── models.py          # Chunk data model
│   │   ├── chunkers.py        # Document chunking strategies
│   │   ├── embeddings.py      # Azure OpenAI embedding pipeline
│   │   ├── search_index.py    # Azure AI Search schema
│   │   ├── indexer.py         # Batch upload to search index
│   │   ├── graph_builder.py   # Cosmos DB Gremlin graph population
│   │   ├── orchestrator.py    # Indexing pipeline orchestration
│   │   ├── change_feed.py     # Real-time indexing via change feed
│   │   └── monitoring.py      # Health monitoring & alerting
│   │
│   ├── search/         # Hybrid search engine
│   │   ├── models.py          # Search result models
│   │   └── hybrid_search.py   # Vector + keyword + graph search
│   │
│   ├── api/            # Phase 3: FastAPI application (56/61 tasks - 92%)
│   │   ├── main.py            # FastAPI app with lifespan management
│   │   ├── dependencies.py    # Dependency injection & settings
│   │   ├── middleware/        # Auth, rate limiting, logging, monitoring
│   │   │   ├── auth.py        # Azure AD JWT authentication
│   │   │   ├── rate_limit.py  # Token bucket rate limiting
│   │   │   ├── logging.py     # Structured logging
│   │   │   └── app_insights.py # Application Insights integration
│   │   ├── models/            # Request/response Pydantic models
│   │   │   ├── search.py      # Search request/response models
│   │   │   ├── resources.py   # Azure resource models
│   │   │   ├── terraform.py   # Terraform resource & plan models
│   │   │   └── git.py         # Git commit & change models
│   │   ├── routers/           # API endpoint routers
│   │   │   ├── search.py      # Search endpoints
│   │   │   ├── resources.py   # Azure resource endpoints
│   │   │   ├── terraform.py   # Terraform endpoints
│   │   │   ├── git.py         # Git history endpoints
│   │   │   └── tools.py       # LLM tool execution endpoints
│   │   ├── services/          # Business logic layer
│   │   │   ├── resource_service.py   # Azure resource operations
│   │   │   ├── terraform_service.py  # Terraform operations
│   │   │   └── git_service.py        # Git operations
│   │   └── tools/             # LLM function calling
│   │       └── definitions.py # 13 tool definitions for LLM
│   │
│   ├── orchestration/  # Phase 4: LLM integration (0/77 tasks)
│   │   └── (not yet implemented)
│   │
│   └── cli/            # CLI tool (not yet implemented)
│
├── frontend/           # React + TypeScript chat UI (not yet implemented)
│
├── tests/              # Test suite (235+ tests passing)
│   ├── unit/           # Unit tests (23+ files)
│   ├── integration/    # Integration tests (4+ files)
│   └── fixtures/       # Test data & fixtures
│       └── terraform/  # Sample .tf files
│
├── config/             # Configuration files
│
├── infrastructure/     # Deployment & monitoring
│   ├── containerapp/   # Azure Container Apps deployment
│   │   ├── containerapp.yaml  # Container App configuration
│   │   ├── deploy.sh          # Automated deployment script
│   │   └── README.md          # Deployment documentation
│   └── monitoring/     # Monitoring & alerting
│       ├── dashboard.json     # Azure Dashboard template
│       ├── alerts.json        # Alert rules & action groups
│       └── README.md          # Monitoring documentation
│
├── Dockerfile          # Container image for API
└── .dockerignore       # Docker build exclusions
```

## Getting Started

See [TASKS.md](./TASKS.md) for the current task list and progress tracking.

See [docs/PLAN.md](./docs/PLAN.md) for the full architecture documentation.

## License

Apache 2.0 License - see [LICENSE](./LICENSE) for details.
