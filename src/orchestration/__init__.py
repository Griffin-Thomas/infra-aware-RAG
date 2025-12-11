"""LLM orchestration and conversation management.

This package provides the core orchestration layer for the infra-aware
RAG assistant, including:

- OrchestrationEngine: LLM integration with Azure OpenAI
- ConversationManager: Multi-turn conversation handling
- MemoryStore: Persistent conversation storage
- Models: Data structures for messages, tool calls, etc.
- Prompts: System prompts and prompt templates

Example:
    from src.orchestration import (
        OrchestrationEngine,
        ConversationManager,
        MemoryStore,
    )

    # Initialize engine
    engine = OrchestrationEngine(
        azure_endpoint="https://my-openai.openai.azure.com",
        model="gpt-4o",
    )

    # Create manager
    manager = ConversationManager(engine)

    # Create conversation
    conv = manager.create_conversation(user_context={"user_name": "Alice"})

    # Send message
    async for response in manager.send_message(conv.id, "List all VMs"):
        if isinstance(response, str):
            print(response, end="")
        else:
            print(f"Done: {response.content}")
"""

from .models import (
    AssistantResponse,
    Conversation,
    ConversationSummary,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
    ToolResult,
    UsageInfo,
)
from .engine import OrchestrationEngine
from .conversation import ConversationManager
from .memory import MemoryStore
from .prompts import (
    get_system_prompt,
    get_plan_analysis_prompt,
    get_error_recovery_prompt,
    get_summarization_prompt,
    get_resource_explanation_prompt,
    SYSTEM_PROMPT_TEMPLATE,
    PLAN_ANALYSIS_PROMPT,
    ERROR_RECOVERY_PROMPT,
    SUMMARIZATION_PROMPT,
)

__all__ = [
    # Models
    "AssistantResponse",
    "Conversation",
    "ConversationSummary",
    "Message",
    "MessageRole",
    "StreamChunk",
    "ToolCall",
    "ToolResult",
    "UsageInfo",
    # Engine
    "OrchestrationEngine",
    # Conversation
    "ConversationManager",
    # Memory
    "MemoryStore",
    # Prompts
    "get_system_prompt",
    "get_plan_analysis_prompt",
    "get_error_recovery_prompt",
    "get_summarization_prompt",
    "get_resource_explanation_prompt",
    "SYSTEM_PROMPT_TEMPLATE",
    "PLAN_ANALYSIS_PROMPT",
    "ERROR_RECOVERY_PROMPT",
    "SUMMARIZATION_PROMPT",
]
