# API Reference

The Infra-Aware RAG API provides RESTful endpoints for searching infrastructure data, managing conversations, and executing LLM tools.

## Base URL

```
http://localhost:8000/api/v1
```

In production, use your deployed API URL.

## Interactive Documentation

When the API server is running, interactive documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## Authentication

All API endpoints (except health checks) require authentication via Azure Entra ID JWT tokens.

### Getting a Token

```bash
# Using Azure CLI
az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv
```

### Using the Token

Include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer <your-token>" \
  http://localhost:8000/api/v1/search \
  -X POST -H "Content-Type: application/json" \
  -d '{"query": "storage accounts"}'
```

---

## Health Endpoints

### GET /health

Basic health check. Returns 200 if the service is running.

**Response:**
```json
{
  "status": "healthy"
}
```

### GET /ready

Readiness check. Returns status of all dependencies.

**Response:**
```json
{
  "status": "ready",
  "dependencies": {
    "search_engine": "ready",
    "cosmos_db": "ready",
    "graph_db": "ready",
    "resource_service": "ready",
    "terraform_service": "ready",
    "git_service": "ready",
    "orchestration_engine": "ready",
    "conversation_manager": "ready"
  }
}
```

---

## Search Endpoints

### POST /api/v1/search

Search across all infrastructure data using hybrid search (vector + keyword).

**Request Body:**
```json
{
  "query": "storage accounts in production",
  "mode": "hybrid",
  "doc_types": ["azure_resource", "terraform_resource"],
  "top": 10,
  "filters": {
    "subscription_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "include_facets": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query text |
| `mode` | string | No | Search mode: `vector`, `keyword`, or `hybrid` (default) |
| `doc_types` | array | No | Filter by document types |
| `top` | integer | No | Number of results (default: 10) |
| `filters` | object | No | Additional filters |
| `include_facets` | boolean | No | Include facet counts |

**Response:**
```json
{
  "results": [
    {
      "id": "doc-123",
      "score": 0.95,
      "content": "Azure Storage Account 'prodstorageacct' in resource group 'rg-production'...",
      "doc_type": "azure_resource",
      "metadata": {
        "resource_id": "/subscriptions/.../storageAccounts/prodstorageacct",
        "resource_type": "Microsoft.Storage/storageAccounts",
        "resource_group": "rg-production"
      },
      "highlights": ["<em>storage</em> account in <em>production</em>"]
    }
  ],
  "total_count": 42,
  "facets": {
    "doc_type": {"azure_resource": 30, "terraform_resource": 12}
  }
}
```

### POST /api/v1/search/expand

Search with graph expansion to find related resources.

**Request Body:**
```json
{
  "query": "main virtual network",
  "top": 5,
  "expand_depth": 2,
  "doc_types": ["azure_resource"]
}
```

---

## Resource Endpoints

### GET /api/v1/resources/{resource_id}

Get details for a specific Azure resource.

**Parameters:**
- `resource_id` (path): Full Azure resource ID (URL-encoded)

**Example:**
```bash
curl "http://localhost:8000/api/v1/resources/subscriptions%2Fxxx%2FresourceGroups%2Frg-prod%2Fproviders%2FMicrosoft.Compute%2FvirtualMachines%2Fvm-web-01"
```

**Response:**
```json
{
  "id": "/subscriptions/.../virtualMachines/vm-web-01",
  "name": "vm-web-01",
  "type": "Microsoft.Compute/virtualMachines",
  "location": "canadaeast",
  "resource_group": "rg-prod",
  "subscription_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "properties": {
    "hardwareProfile": {"vmSize": "Standard_D4s_v3"},
    "osProfile": {"computerName": "vm-web-01"}
  },
  "tags": {"environment": "production"}
}
```

### GET /api/v1/resources/{resource_id}/terraform

Find Terraform code that manages this resource.

**Response:**
```json
[
  {
    "address": "azurerm_virtual_machine.web",
    "type": "azurerm_virtual_machine",
    "file_path": "modules/compute/main.tf",
    "line_number": 45,
    "repo_url": "https://github.com/org/infra",
    "branch": "main",
    "source_code": "resource \"azurerm_virtual_machine\" \"web\" {\n  name = \"vm-web-01\"\n  ..."
  }
]
```

### GET /api/v1/resources/{resource_id}/dependencies

Get resources related through dependencies.

**Parameters:**
- `direction`: `in`, `out`, or `both` (default)
- `depth`: Graph traversal depth 1-5 (default: 2)

**Response:**
```json
[
  {
    "id": "/subscriptions/.../virtualNetworks/vnet-main",
    "name": "vnet-main",
    "type": "Microsoft.Network/virtualNetworks",
    "relationship": "depends_on",
    "direction": "upstream"
  }
]
```

### POST /api/v1/resources/resource-graph/query

Execute a raw Azure Resource Graph KQL query.

**Request Body:**
```json
{
  "query": "Resources | where type == 'microsoft.compute/virtualmachines' | project name, location, resourceGroup | limit 100",
  "subscriptions": ["sub-id-1", "sub-id-2"]
}
```

**Response:**
```json
{
  "results": [
    {"name": "vm-web-01", "location": "canadaeast", "resourceGroup": "rg-prod"},
    {"name": "vm-web-02", "location": "canadaeast", "resourceGroup": "rg-prod"}
  ],
  "total_records": 2
}
```

---

## Terraform Endpoints

### GET /api/v1/terraform/resources

List all Terraform resources.

**Parameters:**
- `type`: Filter by resource type (e.g., `azurerm_virtual_machine`)
- `module`: Filter by module path
- `limit`: Maximum results (default: 100)

**Response:**
```json
{
  "resources": [
    {
      "address": "azurerm_virtual_machine.web",
      "type": "azurerm_virtual_machine",
      "name": "web",
      "module": "module.compute",
      "file_path": "modules/compute/main.tf",
      "line_number": 45
    }
  ],
  "total_count": 156
}
```

### GET /api/v1/terraform/resources/{address}

Get details for a specific Terraform resource.

### GET /api/v1/terraform/plans

List recent Terraform plans.

### GET /api/v1/terraform/plans/{plan_id}

Get details for a specific plan.

### POST /api/v1/terraform/plans/{plan_id}/analyze

Get AI analysis of a Terraform plan.

**Response:**
```json
{
  "summary": "This plan will create 3 new resources and modify 2 existing resources.",
  "risk_level": "MEDIUM",
  "key_changes": [
    "Creating new Azure Storage Account",
    "Modifying network security group rules",
    "Adding new subnet to virtual network"
  ],
  "recommendations": [
    "Review the NSG rule changes carefully",
    "Ensure backup is configured for the new storage account"
  ]
}
```

---

## Git Endpoints

### GET /api/v1/git/commits

List Git commits with optional filtering.

**Parameters:**
- `since`: Start date (ISO 8601)
- `until`: End date (ISO 8601)
- `author`: Filter by author email
- `terraform_only`: Only show commits with Terraform changes
- `limit`: Maximum results (default: 50)

**Response:**
```json
{
  "commits": [
    {
      "sha": "abc123def456",
      "message": "feat: add new storage account for logging",
      "author": "developer@example.com",
      "author_name": "Developer Name",
      "date": "2024-01-15T10:30:00Z",
      "files_changed": 3,
      "insertions": 45,
      "deletions": 12
    }
  ],
  "total_count": 128
}
```

### GET /api/v1/git/commits/{sha}

Get details for a specific commit.

### GET /api/v1/git/commits/{sha}/diff

Get the diff for a specific commit.

---

## Conversation Endpoints

### POST /api/v1/conversations

Create a new conversation.

**Request Body:**
```json
{
  "metadata": {
    "subscription": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

**Response:**
```json
{
  "id": "conv-abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "message_count": 0,
  "metadata": {}
}
```

### GET /api/v1/conversations

List conversations for the current user.

### GET /api/v1/conversations/{id}

Get conversation details.

### DELETE /api/v1/conversations/{id}

Delete a conversation.

### GET /api/v1/conversations/{id}/history

Get message history for a conversation.

### POST /api/v1/conversations/{id}/messages

Send a message and receive the assistant's response.

**Request Body:**
```json
{
  "content": "List all VMs that don't have backup enabled",
  "stream": true
}
```

**Response (SSE Stream):**
```
data: {"type": "token", "content": "I'll search "}
data: {"type": "token", "content": "for virtual machines..."}
data: {"type": "tool_call", "tool_call": {"name": "search_infrastructure", "arguments": {"query": "VMs"}}}
data: {"type": "token", "content": "Based on my search, "}
data: {"type": "complete", "response": {"content": "...", "tool_calls_made": [...], "sources": [...]}}
```

**Non-streaming Response:**

Set `"stream": false` to receive the complete response at once:

```json
{
  "content": "Based on my search, I found 5 virtual machines without backup enabled...",
  "tool_calls_made": [
    {
      "name": "search_infrastructure",
      "arguments": {"query": "VMs without backup"},
      "result_summary": "Found 5 results"
    }
  ],
  "sources": [
    {"type": "azure_resource", "id": "/subscriptions/.../vm-web-01"}
  ],
  "tokens_used": 1250
}
```

---

## Tools Endpoints

### GET /api/v1/tools

List all available LLM tools.

**Response:**
```json
{
  "tools": [
    {
      "name": "search_infrastructure",
      "description": "Search across Azure resources, Terraform code, and Git history",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
      }
    }
  ]
}
```

### POST /api/v1/tools/execute

Execute a specific tool.

**Request Body:**
```json
{
  "name": "search_infrastructure",
  "arguments": {
    "query": "storage accounts",
    "doc_types": ["azure_resource"],
    "top": 5
  }
}
```

---

## Error Responses

All endpoints return standard HTTP status codes:

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful delete) |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid or missing token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found |
| 429 | Too Many Requests - Rate limited |
| 500 | Internal Server Error |

**Error Response Format:**
```json
{
  "detail": "Resource not found: /subscriptions/.../vm-missing"
}
```

---

## Rate Limiting

The API implements token bucket rate limiting:

- **Default limit**: 100 requests per minute per user
- **Burst limit**: 20 requests

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705312800
```

When rate limited, you'll receive a 429 response:
```json
{
  "detail": "Rate limit exceeded. Retry after 60 seconds."
}
```

---

## Pagination

List endpoints support pagination:

```bash
GET /api/v1/git/commits?limit=20&offset=40
```

Response includes pagination info:
```json
{
  "commits": [...],
  "total_count": 128,
  "limit": 20,
  "offset": 40
}
```
