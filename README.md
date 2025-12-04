# Infra-Aware RAG

An AI-powered assistant that answers questions about your Azure cloud infrastructure and Terraform IaC by understanding your live resource state, infrastructure code, and change history.

**⚠️ CRITICAL REQUIREMENT: All Azure resources for this project MUST be deployed in Canada East (`canadaeast`) or Canada Central (`canadacentral`) regions.**

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
├── CLAUDE.md           # Instructions for AI agents working on this project
├── TASKS.md            # Master task list - start here for work items
├── docs/
│   ├── PLAN.md         # Architecture overview
│   ├── 01-data-ingestion.md
│   ├── 02-indexing-and-search.md
│   ├── 03-api-and-tools.md
│   └── 04-llm-orchestration-and-ui.md
├── src/                # Python source code
├── frontend/           # React chat UI
├── tests/              # Test suite
└── infrastructure/     # Terraform for deployment
```

## Getting Started

See [CLAUDE.md](./CLAUDE.md) for project setup and contribution guidelines.

See [TASKS.md](./TASKS.md) for the current task list and progress tracking.

See [docs/PLAN.md](./docs/PLAN.md) for the full architecture documentation.

## Status

**Early Development** - Phase 0 (Project Setup) in progress.

## License

MIT License - see [LICENSE](./LICENSE) for details.
