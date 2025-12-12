# Chat UI User Guide

The Infra-Aware RAG web interface provides a conversational way to query your Azure infrastructure and Terraform configurations.

## Getting Started

### Accessing the Chat UI

1. Open your browser and navigate to the application URL
2. Sign in with your Azure Entra ID credentials
3. You'll be redirected to the chat interface

### Authentication

The chat UI uses Microsoft Authentication Library (MSAL) for secure authentication:

- Click "Sign In" on the login page
- Authenticate with your Azure Entra ID credentials
- Your session will remain active until you sign out or the token expires

## Chat Interface

### Main Components

```
+------------------+----------------------------------------+
|                  |                                        |
|  Conversation    |           Chat Area                    |
|  Sidebar         |                                        |
|                  |  +----------------------------------+  |
|  - New Chat      |  |  Message History                 |  |
|  - History       |  |                                  |  |
|  - Recent        |  |  You: What VMs are in prod?      |  |
|    conversations |  |                                  |  |
|                  |  |  Assistant: I found 5 VMs...     |  |
|                  |  |  [Sources: vm-web-01, vm-web-02] |  |
|                  |  +----------------------------------+  |
|                  |                                        |
|                  |  +----------------------------------+  |
|                  |  | Type your message...        [Send]| |
|                  |  +----------------------------------+  |
+------------------+----------------------------------------+
```

### Conversation Sidebar

The left sidebar shows your conversation history:

- **New Chat**: Start a fresh conversation
- **Recent Conversations**: List of previous conversations
- Click any conversation to resume it
- Conversations are saved automatically

### Message Area

The main chat area displays:

- **Your Messages**: Shown on the right with a blue background
- **Assistant Responses**: Shown on the left with a white background
- **Tool Calls**: Displayed inline when the assistant uses tools
- **Sources**: Referenced resources shown at the bottom of responses

### Input Bar

Type your questions in the input bar at the bottom:

- Press **Enter** or click **Send** to submit
- Press **Shift+Enter** for a new line
- The send button is disabled while waiting for a response

## Asking Questions

### Natural Language Queries

Ask questions in plain English:

```
"What storage accounts do we have in production?"
"Show me all VMs that don't have backup enabled"
"What changed in our network configuration last week?"
"Who modified the main-vnet resource?"
```

### Effective Query Patterns

**Finding Resources:**
```
"List all [resource type] in [environment/subscription/resource group]"
"What [resource type] do we have?"
"Show me resources tagged with [tag]"
```

**Understanding Relationships:**
```
"What depends on [resource name]?"
"What would be affected if I deleted [resource]?"
"Show me the Terraform code for [resource]"
```

**Tracking Changes:**
```
"What changed in [time period]?"
"Who modified [resource] and when?"
"Show me the Git history for [file/resource]"
```

**Analyzing Plans:**
```
"What will this Terraform plan change?"
"Is this plan safe to apply?"
"Explain the changes in plan [plan-id]"
```

## Understanding Responses

### Tool Calls

When the assistant searches for information, you'll see tool calls:

```
Using: search_infrastructure
```

This indicates the assistant is actively querying your infrastructure data.

### Sources

Responses include source references:

- **Azure Resources**: Links to specific resources in your subscription
- **Terraform Files**: References to IaC code with file paths and line numbers
- **Git Commits**: Links to specific commits with author and date

Click on sources to see more details.

### Code Blocks

Terraform code and KQL queries are displayed with syntax highlighting:

```hcl
resource "azurerm_storage_account" "main" {
  name                     = "prodstorageacct"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = "canadaeast"
  account_tier             = "Standard"
  account_replication_type = "GRS"
}
```

## Features

### Streaming Responses

Responses are streamed in real-time:
- Text appears progressively as the assistant generates it
- A blinking cursor indicates the response is still being generated
- You can read the response as it's being written

### Conversation Context

The assistant remembers context within a conversation:

```
You: What VMs are in production?
Assistant: I found 5 VMs: vm-web-01, vm-web-02, vm-api-01, vm-api-02, vm-db-01

You: Which of those don't have backup enabled?
Assistant: Of the 5 production VMs, vm-api-02 and vm-db-01 don't have backup enabled.
```

### Multi-Turn Conversations

Build on previous responses:

```
You: Show me the Terraform for vm-web-01
Assistant: [Shows Terraform code]

You: What module is that in?
Assistant: The vm-web-01 resource is defined in module.compute...

You: Show me all resources in that module
Assistant: [Lists all resources in module.compute]
```

## Tips and Best Practices

### Be Specific

More specific questions get better results:

- Instead of: "Show me VMs"
- Try: "Show me VMs in the rg-production resource group that are running"

### Use Filters

Mention specific attributes to narrow results:

- Subscription: "in the dev subscription"
- Resource group: "in rg-production"
- Tags: "tagged with environment=production"
- Location: "in Canada East"

### Ask Follow-Up Questions

The assistant maintains context, so you can:

1. Start broad: "What storage accounts exist?"
2. Narrow down: "Which of those are in production?"
3. Get details: "Show me the Terraform for the first one"

### Request Specific Formats

Ask for specific output formats:

- "List them in a table"
- "Show the KQL query you used"
- "Give me the resource IDs"

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line in message |
| `Ctrl+K` / `Cmd+K` | New conversation |
| `Escape` | Cancel current request |

## Troubleshooting

### "Something went wrong"

If you see an error message:

1. Try refreshing the page
2. Check if you're still signed in
3. Start a new conversation
4. If the issue persists, check the [Troubleshooting Guide](troubleshooting.md)

### Slow Responses

Complex queries may take longer:

- Tool calls require API requests to Azure services
- Graph traversals for dependencies can be time-consuming
- Large result sets are processed before responding

### Session Expired

If your session expires:

1. You'll be redirected to the login page
2. Sign in again
3. Your conversations are preserved and you can resume them

## Privacy and Security

- All data is transmitted over HTTPS
- Authentication is handled by Azure Entra ID
- Conversations are stored in Cosmos DB with your user ID
- Only you can access your conversation history
- No infrastructure changes are made - the assistant is read-only

## Getting Help

- Use the "?" icon in the header for quick help
- Check the [Troubleshooting Guide](troubleshooting.md) for common issues
- Report bugs via the issue tracker
