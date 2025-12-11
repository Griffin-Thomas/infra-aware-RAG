"""Unit tests for OrchestrationEngine."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.orchestration.engine import OrchestrationEngine
from src.orchestration.models import Message, MessageRole, StreamChunk, ToolCall


class TestOrchestrationEngineInit:
    """Tests for OrchestrationEngine initialization."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI") as mock_client:
            engine = OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                model="gpt-4o",
                api_key="test-key",
            )

            assert engine.model == "gpt-4o"
            assert engine.max_tokens == 4096
            assert engine.temperature == 0.1
            mock_client.assert_called_once()

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI"):
            engine = OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )

            assert engine.model == "gpt-4o"
            assert engine.max_tokens == 4096
            assert engine.temperature == 0.1

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI"):
            engine = OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                model="gpt-4-turbo",
                api_key="test-key",
                max_tokens=2048,
                temperature=0.5,
            )

            assert engine.model == "gpt-4-turbo"
            assert engine.max_tokens == 2048
            assert engine.temperature == 0.5


class TestMessageFormatting:
    """Tests for message formatting methods."""

    @pytest.fixture
    def engine(self):
        """Create engine for testing."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI"):
            return OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )

    def test_format_messages_basic(self, engine):
        """Test formatting basic messages."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="Hello"),
        ]

        formatted = engine._format_messages(messages)

        assert len(formatted) == 2
        assert formatted[0] == {"role": "system", "content": "You are helpful"}
        assert formatted[1] == {"role": "user", "content": "Hello"}

    def test_format_messages_with_tool_calls(self, engine):
        """Test formatting messages with tool calls."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": "{}"},
            }
        ]
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                tool_calls=tool_calls,
            )
        ]

        formatted = engine._format_messages(messages)

        assert formatted[0]["tool_calls"] == tool_calls

    def test_format_messages_tool_response(self, engine):
        """Test formatting tool response messages."""
        messages = [
            Message(
                role=MessageRole.TOOL,
                content='{"result": "data"}',
                tool_call_id="call_1",
                name="search",
            )
        ]

        formatted = engine._format_messages(messages)

        assert formatted[0]["role"] == "tool"
        assert formatted[0]["tool_call_id"] == "call_1"
        assert formatted[0]["name"] == "search"


class TestToolFormatting:
    """Tests for tool formatting."""

    @pytest.fixture
    def engine(self):
        """Create engine for testing."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI"):
            return OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )

    def test_format_tools(self, engine):
        """Test formatting tool definitions."""
        tools = [
            {
                "name": "search_infrastructure",
                "description": "Search for resources",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

        formatted = engine._format_tools(tools)

        assert len(formatted) == 1
        assert formatted[0]["type"] == "function"
        assert formatted[0]["function"]["name"] == "search_infrastructure"
        assert formatted[0]["function"]["description"] == "Search for resources"

    def test_format_multiple_tools(self, engine):
        """Test formatting multiple tools."""
        tools = [
            {"name": "tool1", "description": "First", "parameters": {}},
            {"name": "tool2", "description": "Second", "parameters": {}},
        ]

        formatted = engine._format_tools(tools)

        assert len(formatted) == 2
        assert formatted[0]["function"]["name"] == "tool1"
        assert formatted[1]["function"]["name"] == "tool2"


class TestChatNonStreaming:
    """Tests for non-streaming chat."""

    @pytest.fixture
    def engine(self):
        """Create engine with mocked client."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            engine = OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )
            engine.client = mock_client
            return engine

    @pytest.mark.asyncio
    async def test_chat_simple_response(self, engine):
        """Test simple chat response."""
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="Hello! How can I help?",
                    tool_calls=None,
                ),
                finish_reason="stop",
            )
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        engine.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [Message(role=MessageRole.USER, content="Hello")]

        chunks = []
        async for chunk in engine.chat(messages, stream=False):
            chunks.append(chunk)

        assert len(chunks) == 2  # content + finish
        assert chunks[0].content == "Hello! How can I help?"
        assert chunks[1].finish_reason == "stop"
        assert engine.last_usage is not None
        assert engine.last_usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_chat_with_tool_call(self, engine):
        """Test chat with tool call response."""
        # Mock tool call response
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "search"
        mock_tool_call.function.arguments = '{"query": "VMs"}'

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=None,
                    tool_calls=[mock_tool_call],
                ),
                finish_reason="tool_calls",
            )
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=20, completion_tokens=10, total_tokens=30
        )
        engine.client.chat.completions.create = AsyncMock(return_value=mock_response)

        messages = [Message(role=MessageRole.USER, content="List VMs")]
        tools = [{"name": "search", "description": "Search", "parameters": {}}]

        chunks = []
        async for chunk in engine.chat(messages, tools=tools, stream=False):
            chunks.append(chunk)

        # Should have tool call + finish
        assert any(c.tool_call is not None for c in chunks)
        tool_chunk = next(c for c in chunks if c.tool_call)
        assert tool_chunk.tool_call.name == "search"
        assert tool_chunk.tool_call.arguments == {"query": "VMs"}


class TestProcessNonStreamingResponse:
    """Tests for _process_non_streaming_response."""

    @pytest.fixture
    def engine(self):
        """Create engine for testing."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI"):
            return OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )

    def test_process_content_response(self, engine):
        """Test processing content response."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content="Hello", tool_calls=None),
                finish_reason="stop",
            )
        ]

        chunks = engine._process_non_streaming_response(mock_response)

        assert len(chunks) == 2
        assert chunks[0].content == "Hello"
        assert chunks[1].finish_reason == "stop"

    def test_process_tool_call_response(self, engine):
        """Test processing tool call response."""
        mock_tc = MagicMock()
        mock_tc.id = "call_1"
        mock_tc.function.name = "search"
        mock_tc.function.arguments = '{"q": "test"}'

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content=None, tool_calls=[mock_tc]),
                finish_reason="tool_calls",
            )
        ]

        chunks = engine._process_non_streaming_response(mock_response)

        assert len(chunks) == 2
        assert chunks[0].tool_call is not None
        assert chunks[0].tool_call.name == "search"

    def test_process_invalid_json_arguments(self, engine):
        """Test handling invalid JSON in tool arguments."""
        mock_tc = MagicMock()
        mock_tc.id = "call_1"
        mock_tc.function.name = "search"
        mock_tc.function.arguments = "invalid json"

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content=None, tool_calls=[mock_tc]),
                finish_reason="tool_calls",
            )
        ]

        chunks = engine._process_non_streaming_response(mock_response)

        # Should handle gracefully with empty arguments
        assert chunks[0].tool_call.arguments == {}


class TestTokenCounting:
    """Tests for token counting."""

    @pytest.fixture
    def engine(self):
        """Create engine for testing."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI"):
            return OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )

    @pytest.mark.asyncio
    async def test_count_tokens_fallback(self, engine):
        """Test token counting with fallback."""
        messages = [
            Message(role=MessageRole.USER, content="Hello world, this is a test"),
        ]

        # Even without tiktoken, should return an estimate
        count = await engine.count_tokens(messages)
        assert count > 0

    @pytest.mark.asyncio
    async def test_count_tokens_with_tiktoken(self, engine):
        """Test token counting with tiktoken available."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="Hello"),
        ]

        count = await engine.count_tokens(messages)
        # Should be reasonable token count
        assert count > 0


class TestEngineClose:
    """Tests for engine cleanup."""

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the engine."""
        with patch("src.orchestration.engine.AsyncAzureOpenAI") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client

            engine = OrchestrationEngine(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
            )
            engine.client = mock_client

            await engine.close()

            mock_client.close.assert_called_once()
