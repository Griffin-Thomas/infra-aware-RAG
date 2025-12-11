"""Conversation API request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata to attach to the conversation",
    )


class ConversationResponse(BaseModel):
    """Response containing conversation details."""

    id: str = Field(description="Unique conversation ID")
    created_at: datetime = Field(description="When the conversation was created")
    updated_at: datetime = Field(description="When the conversation was last updated")
    message_count: int = Field(description="Number of messages in the conversation")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional conversation metadata",
    )


class ConversationListResponse(BaseModel):
    """Response containing list of conversations."""

    conversations: list[ConversationResponse] = Field(
        description="List of conversation summaries"
    )
    total_count: int = Field(description="Total number of conversations")


class MessageRequest(BaseModel):
    """Request to send a message in a conversation."""

    content: str = Field(
        min_length=1,
        max_length=10000,
        description="The message content",
    )
    stream: bool = Field(
        default=True,
        description="Whether to stream the response",
    )


class ToolCallInfo(BaseModel):
    """Information about a tool call made during the response."""

    name: str = Field(description="Name of the tool that was called")
    arguments: dict[str, Any] = Field(description="Arguments passed to the tool")
    result_summary: str | None = Field(
        default=None,
        description="Brief summary of the tool result",
    )


class SourceReference(BaseModel):
    """Reference to a source used in the response."""

    type: str = Field(description="Type of source (azure_resource, terraform, git_commit)")
    id: str | None = Field(default=None, description="Resource ID for Azure resources")
    address: str | None = Field(
        default=None,
        description="Terraform resource address",
    )
    sha: str | None = Field(default=None, description="Git commit SHA")
    name: str | None = Field(default=None, description="Resource or commit name")
    file_path: str | None = Field(
        default=None,
        description="File path for Terraform resources",
    )


class MessageResponse(BaseModel):
    """Response from sending a message."""

    content: str = Field(description="The assistant's response content")
    tool_calls_made: list[ToolCallInfo] = Field(
        default_factory=list,
        description="Tools that were called during the response",
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="Sources referenced in the response",
    )
    tokens_used: int = Field(default=0, description="Total tokens used")


class MessageHistoryItem(BaseModel):
    """A single message in conversation history."""

    role: str = Field(description="Message role (user or assistant)")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(description="When the message was sent")


class ConversationHistoryResponse(BaseModel):
    """Response containing conversation history."""

    conversation_id: str = Field(description="Conversation ID")
    messages: list[MessageHistoryItem] = Field(description="List of messages")


class StreamEvent(BaseModel):
    """Event in a streaming response."""

    type: str = Field(
        description="Event type (token, tool_call, complete, error)"
    )
    content: str | None = Field(default=None, description="Token content")
    tool_call: ToolCallInfo | None = Field(
        default=None,
        description="Tool call info",
    )
    response: MessageResponse | None = Field(
        default=None,
        description="Complete response (for 'complete' event)",
    )
    message: str | None = Field(
        default=None,
        description="Error message (for 'error' event)",
    )
