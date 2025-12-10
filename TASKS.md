# Infra-Aware RAG - Master Task List

> **For Agents**: This is the single source of truth for all work. Find an unchecked task (`- [ ]`), read its context, implement it, then mark it complete (`- [x]`).

## Progress Overview

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 0: Project Setup      | ✅ Complete  | 9/9   |
| Phase 1: Data Ingestion     | In Progress | 62/71 |
| Phase 2: Indexing & Search  | In Progress | 46/49 |
| Phase 3: API & Tools        | In Progress | 57/61 |
| Phase 4: LLM & UI           | Not Started | 0/77  |

---

## Phase 0: Project Setup ✅

> **Goal**: Set up the development environment and project scaffolding.
> **Docs**: See `docs/PLAN.md` for technology stack decisions.

### Repository Structure ✅
- [x] Create `src/` directory structure (`ingestion/`, `indexing/`, `api/`, `orchestration/`, `cli/`)
- [x] Create `tests/` directory structure mirroring `src/`
- [x] Create `config/` directory for configuration files
- [x] Create `frontend/` directory for React chat UI
- [x] Create `infrastructure/` directory for deployment Terraform

### Python Project Setup ✅
- [x] Create `pyproject.toml` with project metadata and dependencies
- [x] Create `requirements.txt` for pip compatibility
- [x] Create `requirements-dev.txt` for development dependencies
- [x] Set up pytest configuration (`pytest.ini` or in `pyproject.toml`)

---

## Phase 1: Data Ingestion

> **Goal**: Build connectors to ingest data from Azure, Terraform, and Git sources.
> **Docs**: See `docs/01-data-ingestion.md` for detailed specifications.
> **Milestone 1.1**: Azure integration
> **Milestone 1.2**: Terraform parsing
> **Milestone 1.3**: Git integration

### 1.1 Azure Infrastructure Setup
> Context: `docs/01-data-ingestion.md` → "Setup & Infrastructure" section
> **CRITICAL: All resources MUST be deployed in Canada East or Canada Central**

- [ ] Create Azure Resource Group for the project (in Canada East or Canada Central)
- [ ] Set up Cosmos DB account with NoSQL API (in Canada East or Canada Central)
- [ ] Create Cosmos DB database and containers (`documents`, `conversations`)
- [ ] Set up Azure Service Bus namespace and queue (`ingestion-jobs`) (in Canada East or Canada Central)
- [ ] Configure Azure Key Vault for secrets (in Canada East or Canada Central)
- [ ] Set up Managed Identity for service authentication
- [ ] Create development environment configuration (`config/dev.yaml`) with Canadian region settings

### 1.2 Data Models ✅
> Context: `docs/01-data-ingestion.md` → "Data Model" section

- [x] Create `src/models/__init__.py`
- [x] Implement `AzureResourceDocument` Pydantic model
- [x] Implement `TerraformResourceDocument` Pydantic model
- [x] Implement `TerraformStateDocument` and `TerraformStateResource` models
- [x] Implement `TerraformPlanDocument` and `PlannedChange` models
- [x] Implement `GitCommitDocument` and `GitFileChange` models
- [x] Add `generate_searchable_text()` methods to all document models
- [x] Create JSON schema exports for documentation

### 1.3 Azure Resource Graph Connector ✅
> Context: `docs/01-data-ingestion.md` → "Azure Resource Graph Connector" section
> Code example: Search for `class AzureResourceGraphConnector`

- [x] Create `src/ingestion/__init__.py`
- [x] Create `src/ingestion/connectors/__init__.py`
- [x] Implement `AzureResourceGraphConnector` class in `src/ingestion/connectors/azure_resource_graph.py`
- [x] Add pagination handling for large result sets
- [x] Implement subscription enumeration method
- [x] Add resource type filtering
- [x] Implement `fetch_resource_by_id()` method
- [x] Implement `fetch_resource_types()` summary method
- [x] Add retry logic with exponential backoff
- [x] Create unit tests in `tests/unit/test_azure_resource_graph.py`
- [x] Create integration tests in `tests/integration/test_azure_resource_graph.py`

### 1.4 Terraform HCL Connector ✅
> Context: `docs/01-data-ingestion.md` → "Terraform HCL Connector" section
> Code example: Search for `class TerraformHCLConnector`

- [x] Implement `TerraformHCLConnector` class in `src/ingestion/connectors/terraform_hcl.py`
- [x] Add HCL2 parsing for `.tf` files using `python-hcl2`
- [x] Add JSON parsing for `.tf.json` files
- [x] Implement `_extract_resources()` method
- [x] Implement `_extract_data_sources()` method
- [x] Implement `_extract_variables()` method
- [x] Implement `_extract_outputs()` method
- [x] Implement `_extract_modules()` method
- [x] Implement `_extract_providers()` method
- [x] Track source file and line numbers for each resource
- [x] Create unit tests with sample Terraform files in `tests/unit/test_terraform_hcl.py`

### 1.5 Terraform State Connector
> Context: `docs/01-data-ingestion.md` → "Terraform State Connector" section
> Code example: Search for `class TerraformStateConnector`

- [x] Implement `TerraformStateConnector` class in `src/ingestion/connectors/terraform_state.py`
- [x] Add state file parsing (v4 format)
- [x] Implement `_find_sensitive_attributes()` for secret detection
- [x] Implement `_redact_sensitive()` for sanitizing sensitive data
- [x] Implement `_process_outputs()` with sensitive filtering
- [ ] Add support for reading from Azure Storage backend (future)
- [ ] Handle large state files with streaming (future)
- [x] Create unit tests with sample state files in `tests/unit/test_terraform_state.py`

### 1.6 Terraform Plan Connector ✅
> Context: `docs/01-data-ingestion.md` → "Terraform Plan Document" section

- [x] Create `src/ingestion/connectors/terraform_plan.py`
- [x] Implement plan JSON parsing (`terraform plan -json` output)
- [x] Extract planned changes (create/update/delete/replace)
- [x] Compute attribute-level diffs
- [x] Generate human-readable change summaries
- [x] Create unit tests with sample plan outputs

### 1.7 Git Connector ✅
> Context: `docs/01-data-ingestion.md` → "Git Connector" section
> Code example: Search for `class GitConnector`

- [x] Implement `GitConnector` class in `src/ingestion/connectors/git_connector.py`
- [x] Add repository cloning with authentication support
- [x] Implement commit extraction with date/author filtering
- [x] Implement file change extraction with diff analysis
- [x] Filter for Terraform-related changes (*.tf, *.tfvars, etc.)
- [x] Extract commit metadata (author, committer, message)
- [x] Handle renames, additions, deletions, modifications
- [x] Convert commits to GitCommitDocument
- [x] Create unit tests in `tests/unit/test_git_connector.py`

### 1.8 Ingestion Orchestrator ✅
> Context: `docs/01-data-ingestion.md` → "Ingestion Orchestrator" section
> Code example: Search for `class IngestionOrchestrator`

- [x] Implement `IngestionOrchestrator` class in `src/ingestion/orchestrator.py`
- [x] Implement `IngestionJob`, `JobResult`, `JobStatus` and `IngestionJobType` in `src/ingestion/models.py`
- [x] Add job scheduling via Service Bus (`schedule_job()`)
- [x] Implement job workers/consumers (`start_worker()`)
- [x] Implement `_process_azure_resources()` method
- [x] Implement `_process_terraform_hcl()` method
- [x] Implement `_process_terraform_state()` method
- [x] Implement `_process_terraform_plan()` method
- [x] Implement `_process_git_commits()` method
- [x] Implement `_process_full_sync()` for complete refresh
- [x] Add `_write_document()` for Cosmos DB writes
- [x] Add error handling and dead-letter queue processing
- [x] Create `IngestionConfig` dataclass for configuration
- [x] Add progress tracking and job state management
- [x] Create unit tests in `tests/unit/test_orchestrator.py` and `tests/unit/test_ingestion_models.py` (34 tests, 67% coverage)

---

## Phase 2: Indexing & Search

> **Goal**: Create embeddings, build vector indexes, and establish a graph of relationships.
> **Docs**: See `docs/02-indexing-and-search.md` for detailed specifications.
> **Milestone 2.1**: Embedding pipeline
> **Milestone 2.2**: Vector index
> **Milestone 2.3**: Graph database

### 2.1 Azure Infrastructure for Indexing
> **CRITICAL: All resources MUST be deployed in Canada East or Canada Central**

- [ ] Set up Azure OpenAI resource with `text-embedding-3-large` deployment (in Canada East or Canada Central)
- [ ] Set up Azure AI Search resource (Basic tier for MVP) (in Canada East or Canada Central)
- [ ] Set up Cosmos DB Gremlin API database for graph (in Canada East or Canada Central)

### 2.2 Chunking Pipeline
> Context: `docs/02-indexing-and-search.md` → "Chunking Strategy" section
> Code examples: Search for `class AzureResourceChunker`, `class TerraformResourceChunker`

- [x] Create `src/indexing/__init__.py`
- [x] Create `Chunk` dataclass in `src/indexing/models.py`
- [x] Implement `AzureResourceChunker` in `src/indexing/chunkers.py`
- [x] Implement `TerraformResourceChunker`
- [x] Implement `GitCommitChunker`
- [x] Implement `TerraformPlanChunker` (summary + per-change chunks)
- [x] Add type-specific property extraction for Azure resources
- [x] Create unit tests for all chunkers in `tests/unit/test_chunkers.py`

### 2.3 Embedding Pipeline
> Context: `docs/02-indexing-and-search.md` → "Embedding Pipeline" section
> Code example: Search for `class EmbeddingPipeline`

- [x] Implement `EmbeddingPipeline` class in `src/indexing/embeddings.py`
- [x] Add batching for API efficiency (batch_size=16)
- [x] Implement token counting with tiktoken
- [x] Add text truncation for over-limit chunks
- [x] Implement retry logic with exponential backoff (`_embed_with_retry()`)
- [x] Implement `embed_single()` for query embedding
- [x] Add cost tracking/logging
- [x] Create unit tests in `tests/unit/test_embeddings.py`

### 2.4 Azure AI Search Index
> Context: `docs/02-indexing-and-search.md` → "Azure AI Search Index" section
> Code example: Search for `def create_infra_index()`

- [x] Implement `create_infra_index()` function with full schema in `src/indexing/search_index.py`
- [x] Configure vector search profile (HNSW algorithm)
- [x] Configure semantic search configuration
- [x] Implement `SearchIndexManager` class
- [x] Implement `SearchIndexer` class for batch uploads in `src/indexing/indexer.py`
- [x] Add `delete_documents()` method
- [x] Create integration tests in `tests/integration/test_search_index.py`

### 2.5 Graph Database
> Context: `docs/02-indexing-and-search.md` → "Graph Database Schema" section
> Code example: Search for `class GraphBuilder`

- [x] Implement `GraphBuilder` class in `src/indexing/graph_builder.py`
- [x] Implement `add_subscription()` method
- [x] Implement `add_resource_group()` method with edge to subscription
- [x] Implement `add_azure_resource()` method with edge to resource group
- [x] Implement `add_resource_dependency()` for resource relationships
- [x] Implement `link_terraform_to_azure()` for IaC linkage
- [x] Implement `find_dependencies()` for traversal queries
- [x] Implement `find_terraform_for_resource()`
- [x] Create integration tests in `tests/integration/test_graph_builder.py`

### 2.6 Hybrid Search Engine
> Context: `docs/02-indexing-and-search.md` → "Hybrid Search Implementation" section
> Code example: Search for `class HybridSearchEngine`

- [x] Create `SearchResult` and `HybridSearchResults` dataclasses in `src/search/models.py`
- [x] Implement `HybridSearchEngine` class in `src/search/hybrid_search.py`
- [x] Implement `_vector_search()` method
- [x] Implement `_keyword_search()` method with semantic ranking
- [x] Implement `_hybrid_search()` combining both
- [x] Implement `_build_filter()` for OData expressions
- [x] Implement `search_with_graph_expansion()` for relationship-aware search
- [x] Add facet support
- [x] Create unit tests in `tests/unit/test_hybrid_search.py`

### 2.7 Indexing Pipeline Integration
- [x] Create indexing orchestrator that chains chunking → embedding → indexing
- [x] Integrate with Phase 1 ingestion pipeline (trigger on new documents)
- [x] Add incremental indexing support (only new/changed documents)
- [x] Implement index refresh scheduling
- [x] Add monitoring and alerting for indexing failures

---

## Phase 3: API & Tools

> **Goal**: Build the API layer and define tools the LLM can use.
> **Docs**: See `docs/03-api-and-tools.md` for detailed specifications.
> **Milestone 3.1**: Core API
> **Milestone 3.2**: Full API surface
> **Milestone 3.3**: LLM tools

### 3.1 API Framework Setup ✅
> Context: `docs/03-api-and-tools.md` → "FastAPI Implementation" section

- [x] Create `src/api/__init__.py`
- [x] Create `src/api/main.py` with FastAPI app, lifespan handler, middleware
- [x] Create `src/api/dependencies.py` for shared dependencies (get_search_engine, etc.)
- [x] Add health check endpoint (`/health`)
- [x] Add readiness check endpoint (`/ready`)
- [x] Configure CORS middleware
- [x] Configure OpenAPI/Swagger documentation
- [x] Create Dockerfile for API
- [x] Create Azure Container Apps deployment configuration

### 3.2 Authentication & Authorization
> Context: `docs/03-api-and-tools.md` → "Authentication Middleware" section
> Code example: Search for `class AuthMiddleware`

- [x] Implement `AuthMiddleware` in `src/api/middleware/auth.py`
- [x] Add JWT token validation against Azure AD
- [x] Implement JWKS fetching and caching
- [x] Add user info extraction to request state
- [ ] Implement RBAC based on AAD groups (future)
- [ ] Add subscription-level authorization (future)
- [ ] Create service principal for API
- [ ] Set up Managed Identity for Azure resources

### 3.3 Rate Limiting & Logging ✅
> Context: `docs/03-api-and-tools.md` → "Rate Limiting" section
> Code example: Search for `class RateLimitMiddleware`

- [x] Implement `RateLimitMiddleware` in `src/api/middleware/rate_limit.py`
- [x] Implement `LoggingMiddleware` in `src/api/middleware/logging.py`
- [x] Integrate with Application Insights
- [x] Add usage tracking per user
- [x] Create monitoring dashboards

### 3.4 Search Router ✅
> Context: `docs/03-api-and-tools.md` → "Search Router" section
> Code example: Search for `router = APIRouter()` in search section

- [x] Create `src/api/routers/__init__.py`
- [x] Implement `SearchRequest` and `SearchResponse` models in `src/api/models/`
- [x] Implement `POST /search` endpoint in `src/api/routers/search.py`
- [x] Implement `POST /search/expand` endpoint for graph-expanded search
- [x] Add filtering and faceting support
- [x] Add request validation
- [x] Create unit tests in `tests/unit/test_search_router.py`

### 3.5 Resources Router ✅
> Context: `docs/03-api-and-tools.md` → "Resources Router" section
> Code example: Search for routes starting with `/resources`

- [x] Implement `AzureResource` response model
- [x] Implement `GET /resources/{resource_id}` in `src/api/routers/resources.py`
- [x] Implement `GET /resources/{resource_id}/terraform`
- [x] Implement `GET /resources/{resource_id}/dependencies`
- [x] Implement `POST /resource-graph/query` for raw KQL queries
- [x] Add query validation/sanitization for Resource Graph
- [x] Create unit tests in `tests/unit/test_resources_router.py`

### 3.6 Terraform Router ✅
> Context: `docs/03-api-and-tools.md` → "Terraform Router" section
> Code example: Search for routes starting with `/terraform`

- [x] Implement response models (`TerraformResource`, `TerraformPlan`, `PlanAnalysis`)
- [x] Implement `GET /terraform/resources` in `src/api/routers/terraform.py`
- [x] Implement `GET /terraform/resources/{address}`
- [x] Implement `GET /terraform/plans`
- [x] Implement `GET /terraform/plans/{plan_id}`
- [x] Implement `POST /terraform/plans/{plan_id}/analyze`
- [x] Implement `POST /terraform/plans/parse` for uploading plan JSON
- [x] Create unit tests in `tests/unit/test_terraform_router.py`

### 3.7 Git Router ✅
> Context: `docs/03-api-and-tools.md` → "Git Router" section
> Code example: Search for routes starting with `/git`

- [x] Implement response models (`GitCommit`, `FileChange`)
- [x] Implement `GET /git/commits` in `src/api/routers/git.py`
- [x] Implement `GET /git/commits/{sha}`
- [x] Implement `GET /git/commits/{sha}/diff`
- [x] Add filtering by date range, author, terraform_only
- [x] Create unit tests in `tests/unit/test_git_router.py`

### 3.8 LLM Tool Definitions ✅
> Context: `docs/03-api-and-tools.md` → "LLM Tool Definitions" section
> Code example: Search for `TOOL_DEFINITIONS`

- [x] Create `src/api/tools/__init__.py`
- [x] Define all tool schemas in `src/api/tools/definitions.py`
- [x] Implement `get_tool_definitions()` function
- [x] Implement `get_tool_by_name()` function
- [x] Verify all tools match API endpoints

### 3.9 Tools Router ✅
> Context: `docs/03-api-and-tools.md` → "Tool Router" section
> Code example: Search for `POST /tools/execute`

- [x] Implement `GET /tools` endpoint in `src/api/routers/tools.py`
- [x] Implement `POST /tools/execute` endpoint
- [x] Implement `_execute_tool()` dispatcher function
- [x] Add tool execution logging
- [x] Create unit tests for tool execution in `tests/unit/test_tools_router.py`
- [x] Create integration tests for all tools

---

## Phase 4: LLM Orchestration & UI

> **Goal**: Integrate the LLM, build conversation management, and create user interfaces.
> **Docs**: See `docs/04-llm-orchestration-and-ui.md` for detailed specifications.
> **Milestone 4.1**: Orchestration
> **Milestone 4.2**: Chat UI
> **Milestone 4.3**: CLI & Polish

### 4.1 Orchestration Engine
> Context: `docs/04-llm-orchestration-and-ui.md` → "Orchestration Engine" section
> Code example: Search for `class OrchestrationEngine`

- [ ] Create `src/orchestration/__init__.py`
- [ ] Implement `Message`, `ToolCall`, `StreamChunk` dataclasses in `src/orchestration/models.py`
- [ ] Implement `OrchestrationEngine` class in `src/orchestration/engine.py`
- [ ] Implement `chat()` method with streaming support
- [ ] Implement `_stream_response()` for SSE handling
- [ ] Implement `_format_messages()` for OpenAI API
- [ ] Implement `_format_tools()` for function calling
- [ ] Add retry logic with backoff
- [ ] Handle rate limiting gracefully
- [ ] Add token counting
- [ ] Create unit tests in `tests/unit/test_orchestration_engine.py`

### 4.2 Conversation Manager
> Context: `docs/04-llm-orchestration-and-ui.md` → "Conversation Manager" section
> Code example: Search for `class ConversationManager`

- [ ] Implement `Conversation` dataclass
- [ ] Implement `AssistantResponse` dataclass
- [ ] Implement `ConversationManager` class in `src/orchestration/conversation.py`
- [ ] Implement `create_conversation()` method
- [ ] Implement `send_message()` with tool execution loop
- [ ] Implement `_get_context_messages()` with window management
- [ ] Implement `_execute_tool()` dispatcher
- [ ] Implement `_summarize_messages()` for context compression
- [ ] Implement `_extract_sources()` for citations
- [ ] Create unit tests in `tests/unit/test_conversation_manager.py`

### 4.3 System Prompts
> Context: `docs/04-llm-orchestration-and-ui.md` → "System Prompts" section
> Code example: Search for `SYSTEM_PROMPT_TEMPLATE`

- [ ] Create `src/orchestration/prompts.py`
- [ ] Write main system prompt template
- [ ] Implement `get_system_prompt()` function with context injection
- [ ] Create `PLAN_ANALYSIS_PROMPT` for Terraform plans
- [ ] Create `ERROR_RECOVERY_PROMPT` for fallback handling
- [ ] Test prompts for quality and iterate

### 4.4 Memory Store
> Context: `docs/04-llm-orchestration-and-ui.md` → "Memory Store" section
> Code example: Search for `class MemoryStore`

- [ ] Implement `MemoryStore` class in `src/orchestration/memory.py`
- [ ] Implement `save_conversation()` method
- [ ] Implement `load_conversation()` method
- [ ] Implement `get_user_conversations()` for history
- [ ] Implement `save_user_preference()` method
- [ ] Implement `get_user_preferences()` method
- [ ] Add TTL for old conversations (30 days)
- [ ] Create unit tests in `tests/unit/test_memory_store.py`

### 4.5 Conversation API Endpoints
- [ ] Implement `POST /conversations` endpoint (create new conversation)
- [ ] Implement `GET /conversations` endpoint (list user's conversations)
- [ ] Implement `GET /conversations/{id}` endpoint
- [ ] Implement `POST /conversations/{id}/messages` with SSE streaming
- [ ] Implement `DELETE /conversations/{id}` endpoint

### 4.6 Web Chat UI - Setup
> Context: `docs/04-llm-orchestration-and-ui.md` → "Web Chat UI" section

- [ ] Create `frontend/` directory with React + TypeScript + Vite
- [ ] Configure Tailwind CSS
- [ ] Install Shadcn/UI components
- [ ] Set up React Query for data fetching
- [ ] Configure authentication with Azure AD (MSAL)
- [ ] Create `frontend/src/services/api.ts` for API client
- [ ] Create `frontend/src/services/auth.ts` for auth helpers

### 4.7 Web Chat UI - Components
> Context: `docs/04-llm-orchestration-and-ui.md` → "Main Chat Component" section
> Code example: Search for `ChatContainer.tsx`

- [ ] Implement `ChatContainer` component in `frontend/src/components/Chat/`
- [ ] Implement `MessageList` component
- [ ] Implement `Message` component with Markdown rendering
- [ ] Implement `InputBar` component
- [ ] Implement `ToolCallDisplay` component
- [ ] Implement `CodeBlock` common component
- [ ] Implement `ResourceLink` common component
- [ ] Implement `LoadingIndicator` component

### 4.8 Web Chat UI - Hooks & Features
> Context: `docs/04-llm-orchestration-and-ui.md` → "Chat Hook" section
> Code example: Search for `useChat.ts`

- [ ] Implement `useChat` hook in `frontend/src/hooks/`
- [ ] Implement `useAuth` hook
- [ ] Implement `useStream` hook for SSE handling
- [ ] Add streaming display with cursor animation
- [ ] Add conversation history sidebar
- [ ] Add source/citation display
- [ ] Add error handling and retry UI

### 4.9 Web Chat UI - Deployment
- [ ] Build production bundle
- [ ] Create Azure Static Web Apps configuration
- [ ] Deploy frontend to Azure Static Web Apps
- [ ] Configure custom domain (optional)

### 4.10 CLI Tool
> Context: `docs/04-llm-orchestration-and-ui.md` → "CLI Tool" section
> Code example: Search for `app = typer.Typer`

- [ ] Create `src/cli/__init__.py`
- [ ] Implement main CLI app in `src/cli/main.py`
- [ ] Implement `chat` command (interactive mode)
- [ ] Implement single query mode (`chat "query here"`)
- [ ] Implement `search` command for direct search
- [ ] Implement `query` command for Resource Graph KQL
- [ ] Add rich terminal output (tables, panels, syntax highlighting)
- [ ] Add streaming support with live updates
- [ ] Implement `_get_token()` using Azure CLI
- [ ] Package for distribution via pip
- [ ] Create CLI documentation

---

## Testing Milestones

### Unit Test Coverage
- [ ] All connectors have unit tests (Phase 1)
- [ ] All chunkers have unit tests (Phase 2)
- [ ] Embedding pipeline has unit tests (Phase 2)
- [ ] All API routers have unit tests (Phase 3)
- [ ] Orchestration engine has unit tests (Phase 4)
- [ ] Conversation manager has unit tests (Phase 4)

### Integration Test Coverage
- [ ] Azure Resource Graph connector integration tests
- [ ] Azure AI Search integration tests
- [ ] Cosmos DB integration tests
- [ ] Graph database integration tests
- [ ] Full API integration tests
- [ ] Chat flow integration tests

### End-to-End Tests
- [ ] Complete ingestion → indexing → search pipeline
- [ ] Full conversation with tool usage
- [ ] Web UI E2E tests (Playwright or Cypress)
- [ ] CLI E2E tests

---

## Documentation Tasks

- [ ] Update README.md with project overview and quickstart
- [ ] Create API documentation (auto-generated from OpenAPI)
- [ ] Create user guide for chat UI
- [ ] Create CLI documentation
- [ ] Create deployment guide
- [ ] Create troubleshooting guide
- [ ] Create contribution guide
