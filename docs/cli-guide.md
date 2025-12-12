# CLI User Guide

The Infra-Aware RAG CLI provides a command-line interface for querying your Azure infrastructure and Terraform configurations.

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/Griffin-Thomas/infra-aware-RAG.git
cd infra-aware-RAG

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Verify installation
infra-rag --help
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INFRA_RAG_API_URL` | API base URL | `http://localhost:8000/api/v1` |

Set the API URL if not using the default:

```bash
export INFRA_RAG_API_URL=https://your-api.azurecontainerapps.io/api/v1
```

### Azure Authentication

The CLI uses Azure CLI for authentication. Ensure you're logged in:

```bash
# Login to Azure
az login

# Verify you're logged in
az account show
```

### Check Configuration

```bash
infra-rag config
```

## Commands

### chat

Start an interactive chat session or ask a single question.

#### Interactive Mode

```bash
infra-rag chat
```

This opens an interactive session where you can have a multi-turn conversation.

**Interactive Commands:**
- `exit`, `quit`, or `q` - End the session
- `new` - Start a new conversation

#### Single Query Mode

Ask a one-off question without entering interactive mode:

```bash
infra-rag chat "What VMs are in production?"
```

#### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--subscription` | `-s` | Filter to specific Azure subscription ID |
| `--api-url` | `-u` | Override API base URL |

**Examples:**

```bash
# Interactive mode
infra-rag chat

# Single query
infra-rag chat "List all storage accounts"

# Filter by subscription
infra-rag chat -s "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" "List all VMs"

# Use custom API URL
infra-rag chat -u "https://api.example.com/v1" "What resources exist?"
```

---

### search

Search infrastructure data directly without starting a conversation.

```bash
infra-rag search "storage accounts"
```

#### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--type` | `-t` | Filter by document type | all |
| `--limit` | `-n` | Maximum results | 10 |
| `--mode` | `-m` | Search mode: vector, keyword, hybrid | hybrid |
| `--api-url` | `-u` | Override API base URL | env/default |

**Document Types:**
- `azure_resource` - Azure resources from Resource Graph
- `terraform_resource` - Terraform resource definitions
- `git_commit` - Git commit history
- `terraform_plan` - Terraform plan analysis

**Examples:**

```bash
# Basic search
infra-rag search "virtual machines"

# Filter by type
infra-rag search -t azure_resource "storage accounts"

# More results
infra-rag search -n 20 "network security groups"

# Vector search only
infra-rag search -m vector "production databases"

# Combine options
infra-rag search -t terraform_resource -n 50 -m hybrid "azurerm_virtual_network"
```

**Output:**

Results are displayed in panels with:
- Document type and relevance score
- Content excerpt
- Resource ID or address

---

### query

Execute raw Azure Resource Graph queries using KQL (Kusto Query Language).

```bash
infra-rag query "Resources | limit 10"
```

#### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--subscription` | `-s` | Subscription IDs (can repeat) | all accessible |
| `--output` | `-o` | Output format: table, json, raw | table |
| `--api-url` | `-u` | Override API base URL | env/default |

**Examples:**

```bash
# Simple query
infra-rag query "Resources | limit 10"

# Count by type
infra-rag query "Resources | summarize count() by type | order by count_ desc"

# Filter VMs
infra-rag query "Resources | where type == 'microsoft.compute/virtualmachines' | project name, resourceGroup, location"

# JSON output
infra-rag query -o json "Resources | where type == 'microsoft.storage/storageaccounts'"

# Filter by subscription
infra-rag query -s "sub-id-1" -s "sub-id-2" "Resources | limit 100"
```

**Output Formats:**

- **table** (default): Rich formatted table
- **json**: Raw JSON array for scripting
- **raw**: Minimal output, one result per line

---

### version

Show version information.

```bash
infra-rag version
```

Output:
```
Infra-Aware RAG CLI
Version: 0.1.0

API URL: http://localhost:8000/api/v1
```

---

### config

Show current configuration.

```bash
infra-rag config
```

Displays:
- API URL and its source (env var or default)
- Azure account status from Azure CLI

---

## Usage Examples

### Finding Resources

```bash
# List all VMs
infra-rag chat "What virtual machines do we have?"

# Find specific resource types
infra-rag search -t azure_resource "storage account"

# KQL query for VMs
infra-rag query "Resources | where type == 'microsoft.compute/virtualmachines'"
```

### Understanding Relationships

```bash
# Find dependencies
infra-rag chat "What depends on vnet-main?"

# Find Terraform for a resource
infra-rag chat "Show me the Terraform code for vm-web-01"
```

### Tracking Changes

```bash
# Recent changes
infra-rag chat "What changed in the last week?"

# Git history for a file
infra-rag search -t git_commit "main.tf"
```

### Complex Queries

```bash
# Resources by tag
infra-rag query "Resources | where tags.environment == 'production' | project name, type, resourceGroup"

# Summarize by location
infra-rag query "Resources | summarize count() by location | order by count_ desc"
```

---

## Tips

### Use Specific Queries

More specific queries get better results:

```bash
# Instead of:
infra-rag search "VMs"

# Try:
infra-rag search -t azure_resource "virtual machines in production resource group"
```

### Combine with Shell Tools

```bash
# Pipe JSON output to jq
infra-rag query -o json "Resources | limit 10" | jq '.[].name'

# Save results to file
infra-rag query -o json "Resources" > resources.json
```

### Use Environment Variables

```bash
# Set once in your shell profile
export INFRA_RAG_API_URL=https://your-api.com/api/v1

# Then use without -u flag
infra-rag chat "List all resources"
```

---

## Troubleshooting

### "Could not connect to API"

1. Check if the API server is running
2. Verify the API URL: `infra-rag config`
3. Check network connectivity

### "Warning: Could not get Azure CLI token"

1. Run `az login` to authenticate
2. Check Azure CLI installation: `az --version`
3. The CLI will work without auth for local development

### Slow Responses

- Complex queries may take time
- Graph traversals are particularly slow
- Try narrowing your search with filters

### No Results Found

- Try broader search terms
- Check if data has been ingested
- Verify filters aren't too restrictive

---

## Getting Help

```bash
# Main help
infra-rag --help

# Command-specific help
infra-rag chat --help
infra-rag search --help
infra-rag query --help
```
