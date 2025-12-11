"""Conversation manager for multi-turn LLM interactions.

This module provides the ConversationManager class which handles:
- Conversation state management
- Tool execution loop
- Context management with summarization
- Source extraction for citations
"""

import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, TYPE_CHECKING

from .engine import OrchestrationEngine
from .models import (
    AssistantResponse,
    Conversation,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
    ToolResult,
)
from .prompts import get_system_prompt, get_summarization_prompt

if TYPE_CHECKING:
    from .memory import MemoryStore

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversations with the LLM.

    Handles:
    - Conversation state
    - System prompts
    - Tool execution loop
    - Context management
    - Memory summarization

    Example:
        engine = OrchestrationEngine(...)
        manager = ConversationManager(engine)

        conv = manager.create_conversation(user_context={"user_name": "Alice"})

        async for response in manager.send_message(conv.id, "List all VMs"):
            if isinstance(response, str):
                print(response, end="")  # Streaming content
            else:
                print(f"Final: {response.content}")  # Final response
    """

    MAX_TOOL_ITERATIONS = 10
    MAX_CONTEXT_MESSAGES = 20

    def __init__(
        self,
        engine: OrchestrationEngine,
        memory_store: "MemoryStore | None" = None,
        tool_executor: Any | None = None,
    ):
        """Initialize the conversation manager.

        Args:
            engine: OrchestrationEngine for LLM calls
            memory_store: Optional persistent memory store
            tool_executor: Optional custom tool executor
        """
        self.engine = engine
        self.memory_store = memory_store
        self.tool_executor = tool_executor
        self.conversations: dict[str, Conversation] = {}

        # Import tool definitions
        from src.api.tools.definitions import TOOL_DEFINITIONS

        self.tool_definitions = TOOL_DEFINITIONS

    def create_conversation(
        self,
        user_context: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            user_context: Context about the user (subscriptions, name, etc.)
            conversation_id: Optional specific ID (generates UUID if not provided)

        Returns:
            The created Conversation object
        """
        if conversation_id:
            conv = Conversation(id=conversation_id, metadata=user_context or {})
        else:
            conv = Conversation(metadata=user_context or {})

        # Add system prompt
        system_prompt = get_system_prompt(user_context)
        conv.add_message(
            Message(
                role=MessageRole.SYSTEM,
                content=system_prompt,
            )
        )

        self.conversations[conv.id] = conv
        logger.info(f"Created conversation {conv.id}")
        return conv

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get an existing conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            The Conversation if found, None otherwise
        """
        return self.conversations.get(conversation_id)

    async def load_conversation(self, conversation_id: str) -> Conversation | None:
        """Load a conversation from memory store.

        Args:
            conversation_id: The conversation ID

        Returns:
            The loaded Conversation if found, None otherwise
        """
        # Check in-memory first
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        # Try loading from memory store
        if self.memory_store:
            conv = await self.memory_store.load_conversation(conversation_id)
            if conv:
                self.conversations[conversation_id] = conv
                return conv

        return None

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            True if deleted, False if not found
        """
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            logger.info(f"Deleted conversation {conversation_id}")
            return True
        return False

    async def send_message(
        self,
        conversation_id: str,
        user_message: str,
        stream: bool = True,
    ) -> AsyncIterator[str | AssistantResponse]:
        """Send a user message and get assistant response.

        This method handles the complete conversation loop including:
        - Adding the user message
        - Calling the LLM
        - Executing any tool calls
        - Iterating until a final response

        Args:
            conversation_id: The conversation ID
            user_message: The user's message
            stream: Whether to stream the response

        Yields:
            String chunks during streaming, then final AssistantResponse

        Raises:
            ValueError: If conversation not found
        """
        conv = self.conversations.get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Add user message
        conv.add_message(
            Message(
                role=MessageRole.USER,
                content=user_message,
            )
        )

        # Get context messages (with summarization if needed)
        context_messages = await self._get_context_messages(conv)

        # Run tool loop
        tool_calls_made: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        full_response = ""
        iterations = 0

        while iterations < self.MAX_TOOL_ITERATIONS:
            iterations += 1
            has_tool_calls = False

            async for chunk in self.engine.chat(
                messages=context_messages,
                tools=self.tool_definitions,
                stream=stream and iterations == 1,  # Only stream first response
            ):
                if chunk.content:
                    full_response += chunk.content
                    if stream:
                        yield chunk.content

                if chunk.tool_call:
                    has_tool_calls = True

                    # Execute tool
                    tool_result = await self._execute_tool(chunk.tool_call)
                    tool_calls_made.append(
                        {
                            "name": chunk.tool_call.name,
                            "arguments": chunk.tool_call.arguments,
                            "result_summary": self._summarize_result(tool_result),
                        }
                    )

                    # Extract sources from results
                    if tool_result.success and tool_result.data:
                        sources.extend(self._extract_sources(tool_result.data))

                    # Add tool messages to context
                    context_messages.append(
                        Message(
                            role=MessageRole.ASSISTANT,
                            content="",
                            tool_calls=[
                                {
                                    "id": chunk.tool_call.id,
                                    "type": "function",
                                    "function": {
                                        "name": chunk.tool_call.name,
                                        "arguments": json.dumps(chunk.tool_call.arguments),
                                    },
                                }
                            ],
                        )
                    )
                    context_messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=tool_result.to_content(),
                            tool_call_id=chunk.tool_call.id,
                            name=chunk.tool_call.name,
                        )
                    )

                if chunk.finish_reason == "stop":
                    # Done, no more tool calls
                    break

                if chunk.finish_reason == "tool_calls":
                    # Continue loop to process results
                    break

            # If we got a stop with content, we're done
            if full_response and not has_tool_calls:
                break

            # If no tool calls and no content, something went wrong
            if not has_tool_calls and not full_response:
                logger.warning(f"No response or tool calls in iteration {iterations}")
                break

        # Add assistant response to conversation
        conv.add_message(
            Message(
                role=MessageRole.ASSISTANT,
                content=full_response,
            )
        )

        # Save to memory store
        if self.memory_store:
            try:
                await self.memory_store.save_conversation(conv)
            except Exception as e:
                logger.error(f"Failed to save conversation: {e}")

        # Calculate tokens used if available
        tokens_used = 0
        if self.engine.last_usage:
            tokens_used = self.engine.last_usage.total_tokens

        yield AssistantResponse(
            content=full_response,
            tool_calls_made=tool_calls_made,
            sources=sources,
            tokens_used=tokens_used,
        )

    async def _get_context_messages(self, conv: Conversation) -> list[Message]:
        """Get messages for context, summarizing if needed.

        If the conversation is too long, this will summarize older
        messages to fit within the context window.

        Args:
            conv: The conversation

        Returns:
            List of messages for the API call
        """
        messages = conv.messages.copy()

        if len(messages) > self.MAX_CONTEXT_MESSAGES:
            # Keep system prompt and recent messages
            system_msg = messages[0]
            recent = messages[-(self.MAX_CONTEXT_MESSAGES - 2) :]

            # Summarize older messages
            older = messages[1 : -len(recent)]
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

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool and return results.

        Args:
            tool_call: The tool call to execute

        Returns:
            ToolResult with success status and data/error
        """
        logger.info(f"Executing tool: {tool_call.name}")

        try:
            if self.tool_executor:
                # Use custom executor
                result = await self.tool_executor(tool_call.name, tool_call.arguments)
            else:
                # Use default executor via API tools
                result = await self._default_tool_executor(
                    tool_call.name, tool_call.arguments
                )

            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                success=True,
                data=result,
            )

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_call.name} - {e}")
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                success=False,
                error=str(e),
            )

    async def _default_tool_executor(
        self, name: str, arguments: dict[str, Any]
    ) -> Any:
        """Default tool executor using API services.

        This is a placeholder that should be replaced with actual
        service integration in production.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        # This would integrate with the actual API services
        # For now, return a placeholder
        raise NotImplementedError(
            f"Tool executor not configured for tool: {name}. "
            "Please provide a tool_executor to ConversationManager."
        )

    def _summarize_result(self, result: ToolResult) -> str:
        """Create a brief summary of tool result.

        Args:
            result: The tool result

        Returns:
            Brief summary string
        """
        if not result.success:
            return f"Error: {result.error}"

        data = result.data
        if isinstance(data, dict):
            if "results" in data:
                count = len(data["results"])
                return f"Found {count} result{'s' if count != 1 else ''}"
            if "total_count" in data:
                return f"Total: {data['total_count']} items"
            if "data" in data:
                return "Retrieved data successfully"
        elif isinstance(data, list):
            return f"Found {len(data)} items"

        return "Completed successfully"

    def _extract_sources(self, data: Any) -> list[dict[str, Any]]:
        """Extract source references from tool results.

        Args:
            data: Tool result data

        Returns:
            List of source reference dicts
        """
        sources: list[dict[str, Any]] = []

        if isinstance(data, dict):
            results = data.get("results", [])
            if not isinstance(results, list):
                results = [data]
        elif isinstance(data, list):
            results = data
        else:
            return sources

        for item in results[:5]:  # Limit sources
            if not isinstance(item, dict):
                continue

            source: dict[str, Any] = {}

            if "resource_id" in item:
                source["type"] = "azure_resource"
                source["id"] = item["resource_id"]
                if "name" in item:
                    source["name"] = item["name"]
            elif "address" in item:
                source["type"] = "terraform"
                source["address"] = item["address"]
                if "file_path" in item:
                    source["file_path"] = item["file_path"]
            elif "sha" in item:
                source["type"] = "git_commit"
                source["sha"] = item["sha"][:8]  # Short SHA
                if "message" in item:
                    source["message"] = item["message"][:50]

            if source:
                sources.append(source)

        return sources

    async def _summarize_messages(self, messages: list[Message]) -> str:
        """Summarize a list of messages using the LLM.

        Args:
            messages: Messages to summarize

        Returns:
            Summary text
        """
        # Build conversation text
        conversation_text = "\n".join(
            f"{m.role.value}: {m.content}" for m in messages if m.content
        )

        summary_messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=get_summarization_prompt(conversation_text),
            ),
            Message(
                role=MessageRole.USER,
                content="Please provide the summary.",
            ),
        ]

        full_summary = ""
        async for chunk in self.engine.chat(summary_messages, stream=False):
            if chunk.content:
                full_summary += chunk.content

        return full_summary or "Previous conversation about Azure infrastructure."

    def get_conversation_history(
        self, conversation_id: str
    ) -> list[dict[str, Any]] | None:
        """Get conversation history as a list of message dicts.

        Args:
            conversation_id: The conversation ID

        Returns:
            List of message dicts or None if not found
        """
        conv = self.conversations.get(conversation_id)
        if not conv:
            return None

        return [
            {
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in conv.messages
            if msg.role != MessageRole.SYSTEM  # Exclude system messages
        ]

    def list_conversations(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """List all conversations, optionally filtered by user.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            List of conversation summary dicts
        """
        summaries = []

        for conv in self.conversations.values():
            # Filter by user if specified
            if user_id and conv.metadata.get("user_id") != user_id:
                continue

            # Get preview from first user message
            preview = ""
            for msg in conv.messages:
                if msg.role == MessageRole.USER:
                    preview = msg.content[:100]
                    break

            summaries.append(
                {
                    "id": conv.id,
                    "created_at": conv.created_at.isoformat(),
                    "updated_at": conv.updated_at.isoformat(),
                    "message_count": len(
                        [m for m in conv.messages if m.role != MessageRole.SYSTEM]
                    ),
                    "preview": preview,
                    "metadata": conv.metadata,
                }
            )

        # Sort by updated_at descending
        summaries.sort(key=lambda x: x["updated_at"], reverse=True)
        return summaries
