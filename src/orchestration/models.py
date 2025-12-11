"""Data models for LLM orchestration.

This module defines the core data structures used throughout the
orchestration layer for message handling, tool calls, and streaming.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class MessageRole(str, Enum):
    """Role of a message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Represents a single message in a conversation.

    Attributes:
        role: The role of the message sender
        content: The text content of the message
        tool_calls: List of tool calls made by the assistant (if any)
        tool_call_id: ID of the tool call this message responds to (for tool messages)
        name: Name of the tool (for tool messages)
        timestamp: When the message was created
    """

    role: MessageRole
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for API calls."""
        result: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.name:
            result["name"] = self.name
        return result


@dataclass
class ToolCall:
    """Represents a tool call requested by the LLM.

    Attributes:
        id: Unique identifier for this tool call
        name: Name of the tool to call
        arguments: Arguments to pass to the tool
    """

    id: str
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert tool call to dictionary format."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass
class ToolResult:
    """Result from executing a tool.

    Attributes:
        tool_call_id: ID of the tool call this result is for
        name: Name of the tool that was called
        success: Whether the tool execution succeeded
        data: The result data (if successful)
        error: Error message (if failed)
    """

    tool_call_id: str
    name: str
    success: bool
    data: Any = None
    error: str | None = None

    def to_content(self) -> str:
        """Convert result to content string for the LLM."""
        import json

        if self.success:
            return json.dumps({"success": True, "data": self.data})
        else:
            return json.dumps({"success": False, "error": self.error})


@dataclass
class StreamChunk:
    """A chunk of streaming response from the LLM.

    Attributes:
        content: Text content (if any)
        tool_call: Tool call request (if any)
        finish_reason: Reason for finishing (if done)
    """

    content: str | None = None
    tool_call: ToolCall | None = None
    finish_reason: str | None = None


@dataclass
class Conversation:
    """Represents a conversation session.

    Attributes:
        id: Unique conversation identifier
        messages: List of messages in the conversation
        created_at: When the conversation was created
        updated_at: When the conversation was last updated
        metadata: Additional conversation metadata (user_id, context, etc.)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def user_id(self) -> str | None:
        """Get the user ID from metadata."""
        return self.metadata.get("user_id")

    def add_message(self, message: Message) -> None:
        """Add a message and update timestamp."""
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

    def get_messages_for_api(self) -> list[dict[str, Any]]:
        """Get messages formatted for API calls."""
        return [msg.to_dict() for msg in self.messages]


@dataclass
class AssistantResponse:
    """Complete response from the assistant.

    Attributes:
        content: The text response
        tool_calls_made: List of tools that were called
        sources: Source references extracted from results
        tokens_used: Total tokens used for this response
        finish_reason: How the response ended
    """

    content: str
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    finish_reason: str = "stop"


@dataclass
class UsageInfo:
    """Token usage information.

    Attributes:
        prompt_tokens: Tokens in the prompt
        completion_tokens: Tokens in the completion
        total_tokens: Total tokens used
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ConversationSummary:
    """Summary of a conversation for listings.

    Attributes:
        id: Conversation ID
        created_at: When created
        updated_at: When last updated
        message_count: Number of messages
        preview: Preview of the first user message
        metadata: Additional metadata
    """

    id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    preview: str
    metadata: dict[str, Any] = field(default_factory=dict)
