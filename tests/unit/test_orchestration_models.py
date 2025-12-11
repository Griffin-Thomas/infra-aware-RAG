"""Unit tests for orchestration models."""

import pytest
from datetime import datetime

from src.orchestration.models import (
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


class TestMessageRole:
    """Tests for MessageRole enum."""

    def test_role_values(self):
        """Test role string values."""
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"

    def test_role_from_string(self):
        """Test creating role from string."""
        assert MessageRole("system") == MessageRole.SYSTEM
        assert MessageRole("user") == MessageRole.USER


class TestMessage:
    """Tests for Message dataclass."""

    def test_basic_message(self):
        """Test creating a basic message."""
        msg = Message(
            role=MessageRole.USER,
            content="Hello, world!",
        )
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert msg.name is None
        assert isinstance(msg.timestamp, datetime)

    def test_message_with_tool_calls(self):
        """Test message with tool calls."""
        tool_calls = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "search", "arguments": "{}"},
            }
        ]
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=tool_calls,
        )
        assert msg.tool_calls == tool_calls

    def test_tool_message(self):
        """Test tool response message."""
        msg = Message(
            role=MessageRole.TOOL,
            content='{"success": true}',
            tool_call_id="call_123",
            name="search",
        )
        assert msg.role == MessageRole.TOOL
        assert msg.tool_call_id == "call_123"
        assert msg.name == "search"

    def test_to_dict_basic(self):
        """Test converting message to dict."""
        msg = Message(
            role=MessageRole.USER,
            content="Hello",
        )
        d = msg.to_dict()
        assert d == {"role": "user", "content": "Hello"}

    def test_to_dict_with_tool_calls(self):
        """Test dict conversion with tool calls."""
        tool_calls = [{"id": "call_1", "type": "function"}]
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=tool_calls,
        )
        d = msg.to_dict()
        assert "tool_calls" in d
        assert d["tool_calls"] == tool_calls

    def test_to_dict_tool_message(self):
        """Test dict conversion for tool message."""
        msg = Message(
            role=MessageRole.TOOL,
            content="result",
            tool_call_id="call_1",
            name="search",
        )
        d = msg.to_dict()
        assert d["tool_call_id"] == "call_1"
        assert d["name"] == "search"


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_basic_tool_call(self):
        """Test creating a tool call."""
        tc = ToolCall(
            id="call_123",
            name="search_infrastructure",
            arguments={"query": "VMs"},
        )
        assert tc.id == "call_123"
        assert tc.name == "search_infrastructure"
        assert tc.arguments == {"query": "VMs"}

    def test_to_dict(self):
        """Test converting to dict."""
        tc = ToolCall(
            id="call_123",
            name="search",
            arguments={"q": "test"},
        )
        d = tc.to_dict()
        assert d["id"] == "call_123"
        assert d["type"] == "function"
        assert d["function"]["name"] == "search"
        assert d["function"]["arguments"] == {"q": "test"}


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_success_result(self):
        """Test successful tool result."""
        result = ToolResult(
            tool_call_id="call_123",
            name="search",
            success=True,
            data={"results": [1, 2, 3]},
        )
        assert result.success is True
        assert result.data == {"results": [1, 2, 3]}
        assert result.error is None

    def test_error_result(self):
        """Test error tool result."""
        result = ToolResult(
            tool_call_id="call_123",
            name="search",
            success=False,
            error="Not found",
        )
        assert result.success is False
        assert result.error == "Not found"
        assert result.data is None

    def test_to_content_success(self):
        """Test content conversion for success."""
        result = ToolResult(
            tool_call_id="call_123",
            name="search",
            success=True,
            data={"count": 5},
        )
        content = result.to_content()
        assert '"success": true' in content
        assert '"count": 5' in content

    def test_to_content_error(self):
        """Test content conversion for error."""
        result = ToolResult(
            tool_call_id="call_123",
            name="search",
            success=False,
            error="Failed",
        )
        content = result.to_content()
        assert '"success": false' in content
        assert '"error": "Failed"' in content


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_content_chunk(self):
        """Test content chunk."""
        chunk = StreamChunk(content="Hello")
        assert chunk.content == "Hello"
        assert chunk.tool_call is None
        assert chunk.finish_reason is None

    def test_tool_call_chunk(self):
        """Test tool call chunk."""
        tc = ToolCall(id="1", name="search", arguments={})
        chunk = StreamChunk(tool_call=tc)
        assert chunk.tool_call == tc
        assert chunk.content is None

    def test_finish_chunk(self):
        """Test finish chunk."""
        chunk = StreamChunk(finish_reason="stop")
        assert chunk.finish_reason == "stop"


class TestConversation:
    """Tests for Conversation dataclass."""

    def test_create_conversation(self):
        """Test creating a conversation."""
        conv = Conversation()
        assert conv.id is not None
        assert len(conv.id) == 36  # UUID format
        assert conv.messages == []
        assert isinstance(conv.created_at, datetime)
        assert isinstance(conv.updated_at, datetime)
        assert conv.metadata == {}

    def test_conversation_with_id(self):
        """Test creating conversation with specific ID."""
        conv = Conversation(id="test-123")
        assert conv.id == "test-123"

    def test_conversation_with_metadata(self):
        """Test conversation with metadata."""
        conv = Conversation(metadata={"user_id": "user_123"})
        assert conv.metadata["user_id"] == "user_123"
        assert conv.user_id == "user_123"

    def test_user_id_property(self):
        """Test user_id property."""
        conv = Conversation(metadata={"user_id": "user_456"})
        assert conv.user_id == "user_456"

        conv2 = Conversation()
        assert conv2.user_id is None

    def test_add_message(self):
        """Test adding messages."""
        conv = Conversation()
        original_updated = conv.updated_at

        msg = Message(role=MessageRole.USER, content="Hello")
        conv.add_message(msg)

        assert len(conv.messages) == 1
        assert conv.messages[0] == msg
        assert conv.updated_at >= original_updated

    def test_get_messages_for_api(self):
        """Test getting messages formatted for API."""
        conv = Conversation()
        conv.add_message(Message(role=MessageRole.SYSTEM, content="You are helpful"))
        conv.add_message(Message(role=MessageRole.USER, content="Hello"))

        api_messages = conv.get_messages_for_api()
        assert len(api_messages) == 2
        assert api_messages[0]["role"] == "system"
        assert api_messages[1]["role"] == "user"


class TestAssistantResponse:
    """Tests for AssistantResponse dataclass."""

    def test_basic_response(self):
        """Test basic response."""
        response = AssistantResponse(content="Hello, how can I help?")
        assert response.content == "Hello, how can I help?"
        assert response.tool_calls_made == []
        assert response.sources == []
        assert response.tokens_used == 0
        assert response.finish_reason == "stop"

    def test_response_with_tools(self):
        """Test response with tool calls."""
        response = AssistantResponse(
            content="Found 5 VMs",
            tool_calls_made=[
                {"name": "search", "arguments": {}, "result_summary": "5 results"}
            ],
            tokens_used=150,
        )
        assert len(response.tool_calls_made) == 1
        assert response.tokens_used == 150

    def test_response_with_sources(self):
        """Test response with sources."""
        response = AssistantResponse(
            content="Here are the VMs",
            sources=[
                {"type": "azure_resource", "id": "/sub/123/vm/1"},
                {"type": "terraform", "address": "azurerm_virtual_machine.main"},
            ],
        )
        assert len(response.sources) == 2


class TestUsageInfo:
    """Tests for UsageInfo dataclass."""

    def test_default_values(self):
        """Test default values."""
        usage = UsageInfo()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_with_values(self):
        """Test with provided values."""
        usage = UsageInfo(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


class TestConversationSummary:
    """Tests for ConversationSummary dataclass."""

    def test_create_summary(self):
        """Test creating a summary."""
        now = datetime.utcnow()
        summary = ConversationSummary(
            id="conv_123",
            created_at=now,
            updated_at=now,
            message_count=5,
            preview="What VMs do we have?",
        )
        assert summary.id == "conv_123"
        assert summary.message_count == 5
        assert summary.preview == "What VMs do we have?"
        assert summary.metadata == {}
