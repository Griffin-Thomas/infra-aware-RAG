# Phase 4: LLM Orchestration and UI

## Overview

This phase brings everything together by integrating the LLM for intelligent conversation, building conversation management, and creating user interfaces. We will:

1. **Integrate LLM** with function calling for tool use
2. **Build conversation management** with memory and context
3. **Implement prompt engineering** for infrastructure domain
4. **Create a web-based chat UI**
5. **Build a CLI tool** for terminal users
6. **Optionally develop a VS Code extension**

By the end of this phase, we will have a fully functional infra-aware assistant that users can interact with through multiple interfaces.

---

## Scope

### In Scope
- LLM integration (Azure OpenAI GPT-4o)
- Function calling with tool routing
- Conversation memory (short-term and long-term)
- System prompts and domain-specific instructions
- Web chat UI (React-based)
- Command-line interface
- Response streaming
- Citation and source linking
- Error handling and fallbacks

### Out of Scope (Future)
- VS Code extension (stretch goal)
- Slack/Teams integration
- Voice interface
- Multi-modal (image understanding)
- Fine-tuned models
- Self-hosted LLM options

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            User Interfaces                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Web Chat   │  │     CLI      │  │   VS Code    │  │    API       │     │
│  │   (React)    │  │   (Python)   │  │  Extension   │  │   (Direct)   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Orchestration Layer                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Conversation Manager                           │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │    │
│  │  │  Message   │  │   Tool     │  │  Context   │  │  Memory    │     │    │
│  │  │  Handler   │  │  Router    │  │  Manager   │  │  Store     │     │    │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                      │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         LLM Client                                  │    │
│  │             (Azure OpenAI GPT-4o with Function Calling)             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Tool Layer                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │ Search  │  │Resource │  │Terraform│  │   Git   │  │ Graph   │            │
│  │  Tool   │  │  Tool   │  │  Tool   │  │  Tool   │  │  Tool   │            │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Decisions

### LLM Provider

**Decision:** Azure OpenAI GPT-4o

**Rationale:**
- Best function calling capabilities
- Azure native integration
- Enterprise security and compliance
- Managed Identity support
- Streaming response support

**Model Selection:**
| Use Case | Model | Reasoning |
|----------|-------|-----------|
| Main chat | gpt-4o | Best quality, function calling |
| Plan analysis | gpt-4o | Complex reasoning needed |
| Simple queries | gpt-4o-mini | Cost optimization (future) |

### Chat UI Framework

**Decision:** React with TypeScript

**Rationale:**
- Wide adoption, easy to hire
- Rich ecosystem of components
- Good TypeScript support
- Azure Static Web Apps hosting

**UI Library:** Shadcn/UI with Tailwind CSS

### CLI Framework

**Decision:** Typer (Python)

**Rationale:**
- Built on Click, well-maintained
- Automatic help generation
- Rich terminal output support
- Easy to distribute via pip

---

## LLM Integration

### Orchestration Engine

```python
# src/orchestration/engine.py

from openai import AsyncAzureOpenAI
from typing import AsyncIterator
from dataclasses import dataclass
from enum import Enum

class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

@dataclass
class Message:
    role: MessageRole
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None  # For tool messages

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class StreamChunk:
    content: str | None = None
    tool_call: ToolCall | None = None
    finish_reason: str | None = None

class OrchestrationEngine:
    """
    Main orchestration engine for LLM interactions.

    Handles:
    - Message formatting
    - Function calling
    - Tool execution
    - Response streaming
    """

    def __init__(
        self,
        azure_endpoint: str,
        model: str = "gpt-4o",
        api_key: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        if api_key:
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version="2024-02-01",
            )
        else:
            from azure.identity.aio import DefaultAzureCredential
            credential = DefaultAzureCredential()
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                azure_ad_token_provider=credential.get_token,
                api_version="2024-02-01",
            )

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamChunk]:
        """
        Send messages to LLM and stream response.

        Args:
            messages: Conversation history
            tools: Available tools for function calling
            stream: Whether to stream the response

        Yields:
            StreamChunk objects with content or tool calls
        """
        formatted_messages = self._format_messages(messages)

        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

        if tools:
            kwargs["tools"] = self._format_tools(tools)
            kwargs["tool_choice"] = "auto"

        if stream:
            async for chunk in self._stream_response(**kwargs):
                yield chunk
        else:
            response = await self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    yield StreamChunk(
                        tool_call=ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=json.loads(tc.function.arguments),
                        )
                    )
            else:
                yield StreamChunk(
                    content=choice.message.content,
                    finish_reason=choice.finish_reason,
                )

    async def _stream_response(self, **kwargs) -> AsyncIterator[StreamChunk]:
        """Stream response from OpenAI API."""
        tool_calls = {}

        async with await self.client.chat.completions.create(**kwargs) as response:
            async for chunk in response:
                delta = chunk.choices[0].delta

                # Handle content
                if delta.content:
                    yield StreamChunk(content=delta.content)

                # Handle tool calls (accumulated across chunks)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }

                        if tc_delta.id:
                            tool_calls[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls[idx]["arguments"] += tc_delta.function.arguments

                # Check finish reason
                if chunk.choices[0].finish_reason:
                    # Emit any accumulated tool calls
                    for tc in tool_calls.values():
                        yield StreamChunk(
                            tool_call=ToolCall(
                                id=tc["id"],
                                name=tc["name"],
                                arguments=json.loads(tc["arguments"]) if tc["arguments"] else {},
                            )
                        )

                    yield StreamChunk(finish_reason=chunk.choices[0].finish_reason)

    def _format_messages(self, messages: list[Message]) -> list[dict]:
        """Format messages for OpenAI API."""
        formatted = []
        for msg in messages:
            m = {"role": msg.role.value, "content": msg.content}
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            formatted.append(m)
        return formatted

    def _format_tools(self, tools: list[dict]) -> list[dict]:
        """Format tools for OpenAI API."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                }
            }
            for tool in tools
        ]
```

### Conversation Manager

```python
# src/orchestration/conversation.py

import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import AsyncIterator

from .engine import OrchestrationEngine, Message, MessageRole, StreamChunk, ToolCall
from .prompts import get_system_prompt
from .tools import execute_tool, TOOL_DEFINITIONS

@dataclass
class Conversation:
    """Represents a conversation session."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)

@dataclass
class AssistantResponse:
    """Response from the assistant."""
    content: str
    tool_calls_made: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    tokens_used: int = 0


class ConversationManager:
    """
    Manages conversations with the LLM.

    Handles:
    - Conversation state
    - System prompts
    - Tool execution loop
    - Context management
    - Memory summarization
    """

    MAX_TOOL_ITERATIONS = 10
    MAX_CONTEXT_MESSAGES = 20

    def __init__(
        self,
        engine: OrchestrationEngine,
        memory_store: "MemoryStore | None" = None,
    ):
        self.engine = engine
        self.memory_store = memory_store
        self.conversations: dict[str, Conversation] = {}

    def create_conversation(self, user_context: dict | None = None) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(metadata=user_context or {})

        # Add system prompt
        system_prompt = get_system_prompt(user_context)
        conv.messages.append(Message(
            role=MessageRole.SYSTEM,
            content=system_prompt,
        ))

        self.conversations[conv.id] = conv
        return conv

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get an existing conversation."""
        return self.conversations.get(conversation_id)

    async def send_message(
        self,
        conversation_id: str,
        user_message: str,
        stream: bool = True,
    ) -> AsyncIterator[str | AssistantResponse]:
        """
        Send a user message and get assistant response.

        Yields:
            String chunks during streaming, then final AssistantResponse
        """
        conv = self.conversations.get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Add user message
        conv.messages.append(Message(
            role=MessageRole.USER,
            content=user_message,
        ))
        conv.updated_at = datetime.utcnow()

        # Get context messages (with summarization if needed)
        context_messages = await self._get_context_messages(conv)

        # Run tool loop
        tool_calls_made = []
        sources = []
        full_response = ""
        iterations = 0

        while iterations < self.MAX_TOOL_ITERATIONS:
            iterations += 1

            async for chunk in self.engine.chat(
                messages=context_messages,
                tools=TOOL_DEFINITIONS,
                stream=stream and iterations == 1,  # Only stream first response
            ):
                if chunk.content:
                    full_response += chunk.content
                    if stream:
                        yield chunk.content

                if chunk.tool_call:
                    # Execute tool
                    tool_result = await self._execute_tool(chunk.tool_call)
                    tool_calls_made.append({
                        "name": chunk.tool_call.name,
                        "arguments": chunk.tool_call.arguments,
                        "result_summary": self._summarize_result(tool_result),
                    })

                    # Extract sources from results
                    if isinstance(tool_result, dict):
                        sources.extend(self._extract_sources(tool_result))

                    # Add tool messages to context
                    context_messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content="",
                        tool_calls=[{
                            "id": chunk.tool_call.id,
                            "type": "function",
                            "function": {
                                "name": chunk.tool_call.name,
                                "arguments": json.dumps(chunk.tool_call.arguments),
                            }
                        }],
                    ))
                    context_messages.append(Message(
                        role=MessageRole.TOOL,
                        content=json.dumps(tool_result),
                        tool_call_id=chunk.tool_call.id,
                        name=chunk.tool_call.name,
                    ))

                if chunk.finish_reason == "stop":
                    # Done, no more tool calls
                    break

                if chunk.finish_reason == "tool_calls":
                    # Continue loop to process results
                    continue

            # If we got a stop, break the outer loop too
            if full_response:
                break

        # Add assistant response to conversation
        conv.messages.append(Message(
            role=MessageRole.ASSISTANT,
            content=full_response,
        ))

        # Save to memory store
        if self.memory_store:
            await self.memory_store.save_conversation(conv)

        yield AssistantResponse(
            content=full_response,
            tool_calls_made=tool_calls_made,
            sources=sources,
        )

    async def _get_context_messages(self, conv: Conversation) -> list[Message]:
        """Get messages for context, summarizing if needed."""
        messages = conv.messages.copy()

        if len(messages) > self.MAX_CONTEXT_MESSAGES:
            # Keep system prompt and recent messages
            system_msg = messages[0]
            recent = messages[-(self.MAX_CONTEXT_MESSAGES - 2):]

            # Summarize older messages
            older = messages[1:-len(recent)]
            summary = await self._summarize_messages(older)

            messages = [
                system_msg,
                Message(
                    role=MessageRole.SYSTEM,
                    content=f"Previous conversation summary:\n{summary}",
                ),
                *recent,
            ]

        return messages

    async def _execute_tool(self, tool_call: ToolCall) -> dict:
        """Execute a tool and return results."""
        try:
            result = await execute_tool(tool_call.name, tool_call.arguments)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _summarize_result(self, result: dict) -> str:
        """Create a brief summary of tool result."""
        if not result.get("success"):
            return f"Error: {result.get('error')}"

        data = result.get("data", {})
        if isinstance(data, dict):
            if "results" in data:
                return f"Found {len(data['results'])} results"
            if "total_count" in data:
                return f"Total: {data['total_count']} items"
        return "Completed successfully"

    def _extract_sources(self, result: dict) -> list[dict]:
        """Extract source references from tool results."""
        sources = []
        data = result.get("data", {})

        if isinstance(data, dict) and "results" in data:
            for item in data["results"][:5]:  # Limit sources
                if isinstance(item, dict):
                    source = {}
                    if "resource_id" in item:
                        source["type"] = "azure_resource"
                        source["id"] = item["resource_id"]
                    elif "address" in item:
                        source["type"] = "terraform"
                        source["address"] = item["address"]
                    elif "sha" in item:
                        source["type"] = "git_commit"
                        source["sha"] = item["sha"]

                    if source:
                        sources.append(source)

        return sources

    async def _summarize_messages(self, messages: list[Message]) -> str:
        """Summarize a list of messages."""
        # Use LLM to summarize
        summary_messages = [
            Message(
                role=MessageRole.SYSTEM,
                content="Summarize the following conversation in 2-3 sentences, focusing on key topics and conclusions.",
            ),
            Message(
                role=MessageRole.USER,
                content="\n".join(f"{m.role}: {m.content}" for m in messages),
            ),
        ]

        full_summary = ""
        async for chunk in self.engine.chat(summary_messages, stream=False):
            if chunk.content:
                full_summary += chunk.content

        return full_summary
```

### System Prompts

```python
# src/orchestration/prompts.py

SYSTEM_PROMPT_TEMPLATE = """You are an expert Azure cloud infrastructure assistant. You help users understand, manage, and troubleshoot their Azure infrastructure and Terraform configurations.

## Your Capabilities

You have access to tools that allow you to:
1. **Search** across Azure resources, Terraform code, and Git history
2. **Query** Azure Resource Graph directly using Kusto (KQL)
3. **Retrieve** detailed information about specific resources
4. **Analyze** Terraform plans to explain what will change
5. **Trace** relationships between Azure resources and their Terraform definitions
6. **Show** Git history for infrastructure changes

## How to Respond

1. **Always use tools** to get current information. Never make assumptions about what resources exist.
2. **Be specific** - include resource names, IDs, and file paths in your answers.
3. **Show your work** - explain which tools you used and what you found.
4. **Cite sources** - reference the specific resources, Terraform files, or commits that support your answer.
5. **Handle errors gracefully** - if a tool fails, explain what went wrong and suggest alternatives.

## Query Patterns

When users ask questions, follow these patterns:

**"What resources...?" / "List all..."**
→ Use `search_infrastructure` with appropriate filters, or `query_resource_graph` for complex queries.

**"Show me the Terraform for..."**
→ First find the resource, then use `get_resource_terraform` to find the IaC definition.

**"What changed..." / "Who modified..."**
→ Use `get_git_history` to find relevant commits, then `get_commit_details` for specifics.

**"What will this plan do?"**
→ Use `get_terraform_plan` or `analyze_terraform_plan` for AI-generated analysis.

**"What depends on..." / "What would be affected..."**
→ Use `get_resource_dependencies` to traverse the relationship graph.

## Current Context

{context}

## Important Notes

- You can only READ information, not modify resources.
- Be careful with sensitive information - don't expose secrets or credentials.
- If a query might return too many results, use filters to narrow down.
- Always verify information is current - data may be up to 15 minutes old.
"""

def get_system_prompt(user_context: dict | None = None) -> str:
    """Generate system prompt with user context."""
    context_parts = []

    if user_context:
        if "subscriptions" in user_context:
            subs = user_context["subscriptions"]
            context_parts.append(f"Available subscriptions: {', '.join(subs)}")

        if "user_name" in user_context:
            context_parts.append(f"User: {user_context['user_name']}")

        if "permissions" in user_context:
            context_parts.append(f"Permissions: {user_context['permissions']}")

    context = "\n".join(context_parts) if context_parts else "No specific context provided."

    return SYSTEM_PROMPT_TEMPLATE.format(context=context)


# Additional prompts for specific tasks

PLAN_ANALYSIS_PROMPT = """Analyze this Terraform plan and provide:

1. **Summary**: What are the main changes in 2-3 sentences?
2. **Risk Level**: Rate as LOW, MEDIUM, or HIGH with justification
3. **Key Changes**: List the most important changes (max 5)
4. **Recommendations**: Any concerns or suggestions?

Plan details:
{plan_json}
"""

ERROR_RECOVERY_PROMPT = """The previous tool call failed with error: {error}

Suggest alternative approaches to answer the user's question:
{user_question}

Consider:
- Different tools that might work
- Modified queries
- Manual alternatives the user could try
"""
```

---

## Memory Store

```python
# src/orchestration/memory.py

from azure.cosmos.aio import CosmosClient
from datetime import datetime, timedelta
import json

class MemoryStore:
    """
    Persistent storage for conversation memory.

    Stores:
    - Full conversation history
    - User preferences
    - Frequently accessed resources (for faster retrieval)
    """

    def __init__(
        self,
        cosmos_endpoint: str,
        database_name: str = "infra-rag",
        container_name: str = "conversations",
    ):
        self.cosmos_endpoint = cosmos_endpoint
        self.database_name = database_name
        self.container_name = container_name
        self._client: CosmosClient | None = None

    async def init(self):
        """Initialize Cosmos DB connection."""
        from azure.identity.aio import DefaultAzureCredential
        credential = DefaultAzureCredential()
        self._client = CosmosClient(self.cosmos_endpoint, credential)

    async def save_conversation(self, conversation: "Conversation"):
        """Save conversation to Cosmos DB."""
        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        doc = {
            "id": conversation.id,
            "type": "conversation",
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "metadata": conversation.metadata,
            "messages": [
                {
                    "role": m.role.value,
                    "content": m.content,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                for m in conversation.messages
            ],
            "ttl": 86400 * 30,  # 30 day retention
        }

        await container.upsert_item(doc)

    async def load_conversation(self, conversation_id: str) -> "Conversation | None":
        """Load conversation from Cosmos DB."""
        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        try:
            doc = await container.read_item(conversation_id, partition_key=conversation_id)

            from .conversation import Conversation, Message, MessageRole

            conv = Conversation(
                id=doc["id"],
                created_at=datetime.fromisoformat(doc["created_at"]),
                updated_at=datetime.fromisoformat(doc["updated_at"]),
                metadata=doc.get("metadata", {}),
            )

            for m in doc.get("messages", []):
                conv.messages.append(Message(
                    role=MessageRole(m["role"]),
                    content=m["content"],
                ))

            return conv

        except Exception:
            return None

    async def get_user_conversations(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent conversations for a user."""
        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        query = """
        SELECT c.id, c.created_at, c.updated_at, c.metadata
        FROM c
        WHERE c.type = 'conversation'
        AND c.metadata.user_id = @user_id
        ORDER BY c.updated_at DESC
        OFFSET 0 LIMIT @limit
        """

        results = []
        async for item in container.query_items(
            query,
            parameters=[
                {"name": "@user_id", "value": user_id},
                {"name": "@limit", "value": limit},
            ],
        ):
            results.append(item)

        return results

    async def save_user_preference(self, user_id: str, key: str, value: any):
        """Save a user preference."""
        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        doc = {
            "id": f"pref:{user_id}:{key}",
            "type": "preference",
            "user_id": user_id,
            "key": key,
            "value": value,
            "updated_at": datetime.utcnow().isoformat(),
        }

        await container.upsert_item(doc)

    async def get_user_preferences(self, user_id: str) -> dict:
        """Get all preferences for a user."""
        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        query = """
        SELECT c.key, c.value
        FROM c
        WHERE c.type = 'preference'
        AND c.user_id = @user_id
        """

        prefs = {}
        async for item in container.query_items(
            query,
            parameters=[{"name": "@user_id", "value": user_id}],
        ):
            prefs[item["key"]] = item["value"]

        return prefs

    async def close(self):
        """Close Cosmos DB connection."""
        if self._client:
            await self._client.close()
```

---

## Web Chat UI

### React Application Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Chat/
│   │   │   ├── ChatContainer.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── Message.tsx
│   │   │   ├── InputBar.tsx
│   │   │   └── ToolCallDisplay.tsx
│   │   ├── Sidebar/
│   │   │   ├── ConversationList.tsx
│   │   │   └── SubscriptionFilter.tsx
│   │   └── common/
│   │       ├── CodeBlock.tsx
│   │       ├── ResourceLink.tsx
│   │       └── LoadingIndicator.tsx
│   ├── hooks/
│   │   ├── useChat.ts
│   │   ├── useAuth.ts
│   │   └── useStream.ts
│   ├── services/
│   │   ├── api.ts
│   │   └── auth.ts
│   ├── types/
│   │   └── index.ts
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── tailwind.config.js
```

### Main Chat Component

```tsx
// frontend/src/components/Chat/ChatContainer.tsx

import React, { useState, useRef, useEffect } from 'react';
import { useChat } from '../../hooks/useChat';
import { MessageList } from './MessageList';
import { InputBar } from './InputBar';
import { ToolCallDisplay } from './ToolCallDisplay';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
  sources?: Source[];
  timestamp: Date;
  isStreaming?: boolean;
}

interface ToolCall {
  name: string;
  arguments: Record<string, any>;
  resultSummary?: string;
}

interface Source {
  type: 'azure_resource' | 'terraform' | 'git_commit';
  id?: string;
  address?: string;
  sha?: string;
}

export const ChatContainer: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentToolCalls, setCurrentToolCalls] = useState<ToolCall[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { sendMessage, conversationId, createConversation } = useChat();

  useEffect(() => {
    // Create new conversation on mount
    createConversation();
  }, []);

  useEffect(() => {
    // Scroll to bottom on new messages
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return;

    // Add user message
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);

    // Add placeholder for assistant
    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMessage]);
    setIsLoading(true);
    setCurrentToolCalls([]);

    try {
      await sendMessage(content, {
        onToken: (token: string) => {
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === 'assistant') {
              last.content += token;
            }
            return updated;
          });
        },
        onToolCall: (toolCall: ToolCall) => {
          setCurrentToolCalls(prev => [...prev, toolCall]);
        },
        onComplete: (response: any) => {
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === 'assistant') {
              last.isStreaming = false;
              last.toolCalls = response.toolCallsMade;
              last.sources = response.sources;
            }
            return updated;
          });
          setCurrentToolCalls([]);
        },
        onError: (error: Error) => {
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === 'assistant') {
              last.content = `Error: ${error.message}`;
              last.isStreaming = false;
            }
            return updated;
          });
        },
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-800">
          Infra-Aware Assistant
        </h1>
        <p className="text-sm text-gray-500">
          Ask questions about your Azure infrastructure and Terraform code
        </p>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6">
        <MessageList messages={messages} />

        {/* Tool calls in progress */}
        {currentToolCalls.length > 0 && (
          <ToolCallDisplay toolCalls={currentToolCalls} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <InputBar
        onSend={handleSendMessage}
        disabled={isLoading}
        placeholder="Ask about your infrastructure..."
      />
    </div>
  );
};
```

### Message Component

```tsx
// frontend/src/components/Chat/Message.tsx

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { CodeBlock } from '../common/CodeBlock';
import { ResourceLink } from '../common/ResourceLink';
import { cn } from '../../lib/utils';

interface MessageProps {
  message: {
    role: 'user' | 'assistant';
    content: string;
    sources?: Source[];
    isStreaming?: boolean;
  };
}

export const Message: React.FC<MessageProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-4 p-4 rounded-lg',
        isUser ? 'bg-blue-50' : 'bg-white border'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium',
          isUser ? 'bg-blue-500' : 'bg-purple-500'
        )}
      >
        {isUser ? 'U' : 'A'}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <ReactMarkdown
          components={{
            code: ({ node, inline, className, children, ...props }) => {
              const match = /language-(\w+)/.exec(className || '');
              return !inline && match ? (
                <CodeBlock
                  language={match[1]}
                  value={String(children).replace(/\n$/, '')}
                />
              ) : (
                <code className="bg-gray-100 px-1 rounded" {...props}>
                  {children}
                </code>
              );
            },
          }}
        >
          {message.content}
        </ReactMarkdown>

        {/* Streaming indicator */}
        {message.isStreaming && (
          <span className="inline-block w-2 h-4 bg-purple-500 animate-pulse ml-1" />
        )}

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <h4 className="text-sm font-medium text-gray-500 mb-2">Sources</h4>
            <div className="flex flex-wrap gap-2">
              {message.sources.map((source, index) => (
                <ResourceLink key={index} source={source} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
```

### Chat Hook

```tsx
// frontend/src/hooks/useChat.ts

import { useState, useCallback, useRef } from 'react';
import { useAuth } from './useAuth';

interface ChatCallbacks {
  onToken: (token: string) => void;
  onToolCall: (toolCall: any) => void;
  onComplete: (response: any) => void;
  onError: (error: Error) => void;
}

export const useChat = () => {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const { getAccessToken } = useAuth();
  const abortControllerRef = useRef<AbortController | null>(null);

  const createConversation = useCallback(async () => {
    const token = await getAccessToken();

    const response = await fetch('/api/v1/conversations', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    setConversationId(data.id);
    return data.id;
  }, [getAccessToken]);

  const sendMessage = useCallback(async (
    content: string,
    callbacks: ChatCallbacks
  ) => {
    if (!conversationId) {
      throw new Error('No conversation');
    }

    const token = await getAccessToken();

    // Cancel any existing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(
        `/api/v1/conversations/${conversationId}/messages`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ content }),
          signal: abortControllerRef.current.signal,
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Handle streaming response
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process SSE events
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));

            if (data.type === 'token') {
              callbacks.onToken(data.content);
            } else if (data.type === 'tool_call') {
              callbacks.onToolCall(data.toolCall);
            } else if (data.type === 'complete') {
              callbacks.onComplete(data.response);
            } else if (data.type === 'error') {
              callbacks.onError(new Error(data.message));
            }
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // Request was cancelled
      }
      callbacks.onError(error instanceof Error ? error : new Error('Unknown error'));
    }
  }, [conversationId, getAccessToken]);

  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  return {
    conversationId,
    createConversation,
    sendMessage,
    cancelRequest,
  };
};
```

---

## CLI Tool

```python
# src/cli/main.py

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
import asyncio
import httpx

app = typer.Typer(help="Infra-Aware RAG CLI - Query your Azure infrastructure")
console = Console()

# Configuration
API_BASE_URL = "https://infra-rag.example.com/api/v1"

@app.command()
def chat(
    query: str = typer.Argument(None, help="Initial query (interactive mode if not provided)"),
    subscription: str = typer.Option(None, "--subscription", "-s", help="Filter to subscription"),
):
    """Start an interactive chat session or ask a single question."""
    if query:
        # Single query mode
        asyncio.run(_single_query(query, subscription))
    else:
        # Interactive mode
        asyncio.run(_interactive_chat(subscription))


async def _single_query(query: str, subscription: str | None):
    """Execute a single query."""
    async with httpx.AsyncClient() as client:
        # Get auth token
        token = await _get_token()

        # Create conversation
        conv_resp = await client.post(
            f"{API_BASE_URL}/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        conv_id = conv_resp.json()["id"]

        # Send message with streaming
        console.print()
        with Live(Spinner("dots", text="Thinking..."), refresh_per_second=4) as live:
            response_text = ""

            async with client.stream(
                "POST",
                f"{API_BASE_URL}/conversations/{conv_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": query},
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])

                        if data["type"] == "token":
                            response_text += data["content"]
                            live.update(Markdown(response_text))

                        elif data["type"] == "tool_call":
                            live.update(
                                Panel(
                                    f"Using tool: {data['toolCall']['name']}",
                                    title="Tool",
                                    border_style="yellow",
                                )
                            )

                        elif data["type"] == "complete":
                            live.update(Markdown(response_text))

        console.print()


async def _interactive_chat(subscription: str | None):
    """Run interactive chat mode."""
    console.print(Panel(
        "Welcome to Infra-Aware RAG CLI\n"
        "Ask questions about your Azure infrastructure.\n"
        "Type 'exit' or 'quit' to end the session.",
        title="Interactive Mode",
        border_style="blue",
    ))

    async with httpx.AsyncClient() as client:
        token = await _get_token()

        # Create conversation
        conv_resp = await client.post(
            f"{API_BASE_URL}/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        conv_id = conv_resp.json()["id"]

        while True:
            console.print()
            query = console.input("[bold blue]You:[/bold blue] ")

            if query.lower() in ("exit", "quit", "q"):
                console.print("Goodbye!")
                break

            if not query.strip():
                continue

            console.print()
            console.print("[bold purple]Assistant:[/bold purple]")

            response_text = ""

            async with client.stream(
                "POST",
                f"{API_BASE_URL}/conversations/{conv_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": query},
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])

                        if data["type"] == "token":
                            console.print(data["content"], end="")
                            response_text += data["content"]

                        elif data["type"] == "tool_call":
                            console.print(
                                f"\n[yellow]→ Using: {data['toolCall']['name']}[/yellow]",
                                end=""
                            )

                        elif data["type"] == "complete":
                            console.print()  # Newline

            console.print()


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    type: str = typer.Option(None, "--type", "-t", help="Filter by doc type"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
):
    """Search infrastructure without starting a conversation."""
    asyncio.run(_search(query, type, limit))


async def _search(query: str, doc_type: str | None, limit: int):
    """Execute a direct search."""
    async with httpx.AsyncClient() as client:
        token = await _get_token()

        body = {"query": query, "top": limit}
        if doc_type:
            body["doc_types"] = [doc_type]

        response = await client.post(
            f"{API_BASE_URL}/search",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )

        data = response.json()

        console.print(f"\nFound {data['total_count']} results:\n")

        for result in data["results"]:
            console.print(Panel(
                result["content"][:500] + ("..." if len(result["content"]) > 500 else ""),
                title=f"{result['doc_type']} | Score: {result['score']:.3f}",
                border_style="green",
            ))


@app.command()
def query(
    kql: str = typer.Argument(..., help="Kusto query for Azure Resource Graph"),
):
    """Execute a raw Azure Resource Graph query."""
    asyncio.run(_resource_graph_query(kql))


async def _resource_graph_query(kql: str):
    """Execute Resource Graph query."""
    async with httpx.AsyncClient() as client:
        token = await _get_token()

        response = await client.post(
            f"{API_BASE_URL}/resource-graph/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": kql},
        )

        data = response.json()

        # Display as table
        from rich.table import Table

        if data.get("results"):
            results = data["results"]
            if results:
                # Create table from first result's keys
                table = Table(show_header=True)
                for key in results[0].keys():
                    table.add_column(key)

                for row in results[:50]:  # Limit display
                    table.add_row(*[str(v)[:50] for v in row.values()])

                console.print(table)
                console.print(f"\nShowing {min(50, len(results))} of {len(results)} results")
        else:
            console.print("No results found")


async def _get_token() -> str:
    """Get authentication token."""
    # Use Azure CLI token
    import subprocess
    result = subprocess.run(
        ["az", "account", "get-access-token", "--query", "accessToken", "-o", "tsv"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    app()
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_orchestration.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.orchestration.conversation import ConversationManager, Message, MessageRole

@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    return engine

@pytest.fixture
def conversation_manager(mock_engine):
    return ConversationManager(engine=mock_engine)

class TestConversationManager:

    def test_create_conversation(self, conversation_manager):
        """Test creating a new conversation."""
        conv = conversation_manager.create_conversation()

        assert conv.id is not None
        assert len(conv.messages) == 1
        assert conv.messages[0].role == MessageRole.SYSTEM

    @pytest.mark.asyncio
    async def test_send_message_simple(self, conversation_manager, mock_engine):
        """Test sending a simple message without tool calls."""
        mock_engine.chat.return_value = async_generator([
            MagicMock(content="Hello!", tool_call=None, finish_reason="stop"),
        ])

        conv = conversation_manager.create_conversation()

        responses = []
        async for response in conversation_manager.send_message(
            conv.id,
            "Hi there",
            stream=False,
        ):
            responses.append(response)

        assert len(responses) > 0
        # Last response should be AssistantResponse
        final = responses[-1]
        assert final.content == "Hello!"

    @pytest.mark.asyncio
    async def test_send_message_with_tool(self, conversation_manager, mock_engine):
        """Test message that triggers tool use."""
        mock_engine.chat.side_effect = [
            # First call: tool call
            async_generator([
                MagicMock(
                    content=None,
                    tool_call=MagicMock(
                        id="call-1",
                        name="search_infrastructure",
                        arguments={"query": "VMs"},
                    ),
                    finish_reason="tool_calls",
                ),
            ]),
            # Second call: final response
            async_generator([
                MagicMock(content="Found 5 VMs.", tool_call=None, finish_reason="stop"),
            ]),
        ]

        conv = conversation_manager.create_conversation()

        responses = []
        async for response in conversation_manager.send_message(
            conv.id,
            "List all VMs",
            stream=False,
        ):
            responses.append(response)

        final = responses[-1]
        assert "Found 5 VMs" in final.content
        assert len(final.tool_calls_made) > 0


async def async_generator(items):
    for item in items:
        yield item
```

### Integration Tests

```python
# tests/integration/test_chat_flow.py

import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_chat_flow(api_base_url, auth_token):
    """Test complete chat flow."""
    async with AsyncClient(base_url=api_base_url) as client:
        headers = {"Authorization": f"Bearer {auth_token}"}

        # Create conversation
        conv_resp = await client.post("/api/v1/conversations", headers=headers)
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["id"]

        # Send message
        msg_resp = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=headers,
            json={"content": "List all storage accounts"},
        )
        assert msg_resp.status_code == 200

        # Verify response includes results
        # (would need to parse SSE stream in real test)
```

---

## Demo Strategy

### Demo 1: Basic Chat
**Goal:** Show natural language interaction.

**Steps:**
1. Open chat UI
2. Ask: "What VMs do we have in production?"
3. Show assistant using search tool
4. Show formatted response with sources

### Demo 2: Tool Usage
**Goal:** Show multi-step tool usage.

**Steps:**
1. Ask: "Show me the Terraform for our main database"
2. Watch assistant: search → get resource → find terraform
3. Show source code in response

### Demo 3: Complex Query
**Goal:** Show complex reasoning.

**Steps:**
1. Ask: "What would be affected if we deleted the main-vnet?"
2. Watch assistant use graph traversal
3. Show dependency tree in response

### Demo 4: CLI
**Goal:** Show terminal workflow.

**Steps:**
1. Run: `infra-rag chat "List all resources missing backup"`
2. Show streaming output
3. Run: `infra-rag query "Resources | summarize count() by type"`
4. Show table output

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM hallucinations | Wrong information | Ground with retrieved data; show sources |
| Slow response times | Poor UX | Streaming; progress indicators; caching |
| Token limit exceeded | Truncated context | Conversation summarization |
| Tool errors | Broken responses | Graceful error handling; retries |
| UI complexity | User confusion | Progressive disclosure; examples |
| Cost per conversation | Budget overruns | Token budgets; cheaper models for simple queries |

---

## Open Questions

1. **Conversation persistence:** How long should conversations be stored?
2. **Sharing:** Can users share conversations with teammates?
3. **Feedback:** Should we add thumbs up/down for response quality?
4. **Caching:** Should we cache common queries?
5. **Offline mode:** Should CLI support offline/cached mode?

---

## Task List

> **See [TASKS.md](../TASKS.md)** for the authoritative task list.
>
> Tasks for this phase are under **"Phase 4: LLM Orchestration & UI"** including:
> - 4.1 Orchestration Engine
> - 4.2 Conversation Manager
> - 4.3 System Prompts
> - 4.4 Memory Store
> - 4.5 Conversation API Endpoints
> - 4.6 Web Chat UI - Setup
> - 4.7 Web Chat UI - Components
> - 4.8 Web Chat UI - Hooks & Features
> - 4.9 Web Chat UI - Deployment
> - 4.10 CLI Tool

---

## Dependencies

```
# requirements.txt (Phase 4 additions)

# LLM
openai>=1.6.0

# CLI
typer>=0.9.0
rich>=13.7.0

# Streaming
sse-starlette>=1.8.0

# Frontend (package.json)
# react: ^18.2.0
# typescript: ^5.3.0
# @tanstack/react-query: ^5.0.0
# tailwindcss: ^3.4.0
# react-markdown: ^9.0.0
```

---

## Milestones

### Milestone 4.1: Orchestration (End of Week 10)
- LLM integration working
- Tool execution loop complete
- Conversation management operational
- Basic prompts working

### Milestone 4.2: Chat UI (End of Week 11)
- React chat application working
- Streaming display functional
- Authentication integrated
- Deployed to Azure

### Milestone 4.3: CLI & Polish (End of Week 12)
- CLI tool complete and packaged
- Error handling refined
- Performance optimized
- Documentation complete
- MVP ready for users

---

## Post-MVP Roadmap

After completing the MVP, consider these enhancements:

1. **VS Code Extension**
   - Inline infrastructure queries
   - Terraform validation integration
   - Resource hover information

2. **Slack/Teams Bot**
   - Chat in team channels
   - Incident response integration
   - Scheduled reports

3. **Advanced Features**
   - Anomaly detection alerts
   - Cost optimization suggestions
   - Compliance scanning
   - Drift detection

4. **Enterprise Features**
   - Multi-tenant support
   - SSO integration
   - Audit logging
   - Custom tool development

5. **Model Improvements**
   - Fine-tuned embeddings
   - Domain-specific model fine-tuning
   - Local model support (Ollama)
