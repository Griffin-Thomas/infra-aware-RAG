# Infra-Aware RAG

An AI-powered assistant that answers questions about your Azure cloud infrastructure and Terraform IaC by understanding your live resource state, infrastructure code, and change history.

## What It Does

Ask natural language questions like:
- "Which VMs in production don't have backup enabled?"
- "What changed in our network configuration last week?"
- "Show me the Terraform code for this load balancer"
- "What will this Terraform plan change?"

## Frontend Preview

![Frontend chat interface](docs/assets/frontend-chat-interface.png)

## Data Sources

- **Azure Resource Graph** - Live state of all Azure resources
- **Terraform** - HCL code, state files, and plan analysis
- **Git History** - Who changed what and when

## Tech Stack

All Azure services deployed in **Canada East** or **Canada Central**:

- **Backend**: Python 3.11+, FastAPI
- **LLM**: Azure OpenAI (GPT-4o)
- **Search**: Azure AI Search (vector + keyword hybrid)
- **Graph**: Cosmos DB Gremlin API
- **Storage**: Cosmos DB NoSQL
- **Frontend**: React + TypeScript + Vite
- **CLI**: Typer + Rich

## Quick Start

### Prerequisites

- Python 3.11 or later
- Node.js 18+ (for frontend)
- Azure CLI (`az`) installed and logged in
- Azure subscription with required services

### 1. Clone and Setup

```bash
git clone https://github.com/Griffin-Thomas/infra-aware-RAG.git
cd infra-aware-RAG

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For development
pip install -r requirements-dev.txt
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your Azure resource endpoints
```

Required environment variables:

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_INDEX_NAME=infra-index

# Cosmos DB
COSMOS_DB_ENDPOINT=https://your-cosmos.documents.azure.com
COSMOS_DB_DATABASE=infra-rag

# Authentication (Entra ID)
AZURE_AD_TENANT_ID=your-tenant-id
AZURE_AD_CLIENT_ID=your-client-id
```

### 3. Run the API Server

```bash
# Development mode with auto-reload
uvicorn src.api.main:app --reload --port 8000

# The API will be available at http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
```

### 4. Run the Frontend (Optional)

```bash
cd frontend
npm install
npm run dev

# Frontend will be available at http://localhost:5173
```

### 5. Use the CLI

```bash
# Install the CLI
pip install -e .

# Interactive chat
infra-rag chat

# Single query
infra-rag chat "List all storage accounts"

# Search infrastructure
infra-rag search "virtual machines" --type azure_resource

# Execute KQL query
infra-rag query "Resources | summarize count() by type"
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/PLAN.md) | System architecture and design decisions |
| [Data Ingestion](docs/01-data-ingestion.md) | How data is collected from Azure, Terraform, Git |
| [Indexing & Search](docs/02-indexing-and-search.md) | Embedding pipeline and hybrid search |
| [API Reference](docs/03-api-and-tools.md) | REST API endpoints and LLM tools |
| [LLM & UI](docs/04-llm-orchestration-and-ui.md) | Chat orchestration and interfaces |
| [CLI Guide](docs/cli-guide.md) | Command-line interface usage |
| [Chat UI Guide](docs/chat-ui-guide.md) | Web chat interface usage |
| [Deployment Guide](docs/deployment-guide.md) | Production deployment instructions |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [Contributing](docs/contributing.md) | How to contribute to the project |

## API Endpoints

The API is available at `/api/v1/` with the following main routes:

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/search` | Hybrid search across all infrastructure data |
| `GET /api/v1/resources/{id}` | Get Azure resource details |
| `GET /api/v1/terraform/resources` | List Terraform resources |
| `GET /api/v1/git/commits` | Get Git commit history |
| `POST /api/v1/conversations` | Create a new chat conversation |
| `POST /api/v1/conversations/{id}/messages` | Send a message (SSE streaming) |
| `POST /api/v1/tools/execute` | Execute an LLM tool |

Full API documentation is available at `/docs` (Swagger UI) or `/redoc` (ReDoc) when the server is running.

## Project Structure

```
/
├── src/                   # Python source code
│   ├── api/               # FastAPI application
│   ├── cli/               # Command-line interface
│   ├── ingestion/         # Data connectors
│   ├── indexing/          # Embedding & search indexing
│   ├── orchestration/     # LLM chat orchestration
│   ├── search/            # Hybrid search engine
│   └── models/            # Pydantic data models
├── frontend/              # React + TypeScript UI
├── tests/                 # Test suite (600+ tests)
├── docs/                  # Documentation
├── infrastructure/        # Deployment configs
└── config/                # Configuration files
```

## Running Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
python -m pytest tests/unit/test_cli.py -v
```

## Development Progress

See [TASKS.md](./TASKS.md) for the current task list and progress tracking.

## License

MIT License - see [LICENSE](./LICENSE) for details.
