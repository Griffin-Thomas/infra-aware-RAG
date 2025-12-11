"""Unit tests for ConversationManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.orchestration.conversation import ConversationManager
from src.orchestration.models import (
    AssistantResponse,
    Conversation,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
    ToolResult,
)


# Patch the import in the conversation module
@pytest.fixture(autouse=True)
def mock_tool_definitions():
    """Mock TOOL_DEFINITIONS for all tests."""
    with patch.dict(
        "sys.modules",
        {"src.api.tools.definitions": MagicMock(TOOL_DEFINITIONS=[])}
    ):
        # Need to reload the module to pick up the mock
        import importlib
        import src.orchestration.conversation
        importlib.reload(src.orchestration.conversation)
        yield
        # Reload again to restore original
        importlib.reload(src.orchestration.conversation)


class TestConversationManagerInit:
    """Tests for ConversationManager initialization."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock engine."""
        engine = AsyncMock()
        return engine

    def test_init(self, mock_engine):
        """Test basic initialization."""
        from src.orchestration.conversation import ConversationManager
        manager = ConversationManager(engine=mock_engine)

        assert manager.engine == mock_engine
        assert manager.memory_store is None
        assert manager.conversations == {}

    def test_init_with_memory_store(self, mock_engine):
        """Test initialization with memory store."""
        from src.orchestration.conversation import ConversationManager
        mock_memory = AsyncMock()
        manager = ConversationManager(
            engine=mock_engine,
            memory_store=mock_memory,
        )

        assert manager.memory_store == mock_memory


class TestCreateConversation:
    """Tests for creating conversations."""

    @pytest.fixture
    def manager(self):
        """Create manager for testing."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        return ConversationManager(engine=mock_engine)

    def test_create_conversation_basic(self, manager):
        """Test creating a basic conversation."""
        conv = manager.create_conversation()

        assert conv.id is not None
        assert len(conv.messages) == 1  # System prompt
        assert conv.messages[0].role == MessageRole.SYSTEM
        assert conv.id in manager.conversations

    def test_create_conversation_with_user_context(self, manager):
        """Test creating conversation with user context."""
        context = {
            "user_name": "Alice",
            "subscriptions": ["sub-1", "sub-2"],
        }
        conv = manager.create_conversation(user_context=context)

        assert conv.metadata == context
        # System prompt should include context
        assert "Alice" in conv.messages[0].content or "sub-1" in conv.messages[0].content

    def test_create_conversation_with_specific_id(self, manager):
        """Test creating conversation with specific ID."""
        conv = manager.create_conversation(conversation_id="my-conv-123")

        assert conv.id == "my-conv-123"
        assert "my-conv-123" in manager.conversations


class TestGetConversation:
    """Tests for getting conversations."""

    @pytest.fixture
    def manager(self):
        """Create manager with a conversation."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        manager = ConversationManager(engine=mock_engine)
        manager.create_conversation(conversation_id="test-conv")
        return manager

    def test_get_existing_conversation(self, manager):
        """Test getting existing conversation."""
        conv = manager.get_conversation("test-conv")
        assert conv is not None
        assert conv.id == "test-conv"

    def test_get_nonexistent_conversation(self, manager):
        """Test getting non-existent conversation."""
        conv = manager.get_conversation("does-not-exist")
        assert conv is None


class TestDeleteConversation:
    """Tests for deleting conversations."""

    @pytest.fixture
    def manager(self):
        """Create manager with a conversation."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        manager = ConversationManager(engine=mock_engine)
        manager.create_conversation(conversation_id="test-conv")
        return manager

    def test_delete_existing_conversation(self, manager):
        """Test deleting existing conversation."""
        result = manager.delete_conversation("test-conv")
        assert result is True
        assert "test-conv" not in manager.conversations

    def test_delete_nonexistent_conversation(self, manager):
        """Test deleting non-existent conversation."""
        result = manager.delete_conversation("does-not-exist")
        assert result is False


class TestSendMessage:
    """Tests for sending messages."""

    @pytest.fixture
    def manager(self):
        """Create manager with mocked engine."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        manager = ConversationManager(engine=mock_engine)
        return manager

    @pytest.mark.asyncio
    async def test_send_message_simple(self, manager):
        """Test sending a simple message."""
        # Setup mock response
        async def mock_chat(*args, **kwargs):
            yield StreamChunk(content="Hello!")
            yield StreamChunk(finish_reason="stop")

        manager.engine.chat = mock_chat

        conv = manager.create_conversation()

        responses = []
        async for response in manager.send_message(conv.id, "Hi there"):
            responses.append(response)

        # Should have content chunks and final response
        assert len(responses) >= 1
        # Last should be AssistantResponse
        final = responses[-1]
        assert isinstance(final, AssistantResponse)
        assert final.content == "Hello!"

    @pytest.mark.asyncio
    async def test_send_message_not_found(self, manager):
        """Test sending to non-existent conversation."""
        with pytest.raises(ValueError, match="not found"):
            async for _ in manager.send_message("fake-id", "Hello"):
                pass

    @pytest.mark.asyncio
    async def test_send_message_adds_user_message(self, manager):
        """Test that user message is added to conversation."""
        async def mock_chat(*args, **kwargs):
            yield StreamChunk(content="Response")
            yield StreamChunk(finish_reason="stop")

        manager.engine.chat = mock_chat

        conv = manager.create_conversation()
        initial_count = len(conv.messages)

        async for _ in manager.send_message(conv.id, "User message"):
            pass

        # Should have added user message and assistant response
        assert len(conv.messages) == initial_count + 2

    @pytest.mark.asyncio
    async def test_send_message_streaming(self, manager):
        """Test streaming response."""
        async def mock_chat(*args, **kwargs):
            yield StreamChunk(content="Hello")
            yield StreamChunk(content=" world")
            yield StreamChunk(content="!")
            yield StreamChunk(finish_reason="stop")

        manager.engine.chat = mock_chat

        conv = manager.create_conversation()

        content_chunks = []
        async for response in manager.send_message(conv.id, "Hi", stream=True):
            if isinstance(response, str):
                content_chunks.append(response)

        assert "".join(content_chunks) == "Hello world!"


class TestToolExecution:
    """Tests for tool execution."""

    @pytest.fixture
    def manager(self):
        """Create manager with tool executor."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        mock_executor = AsyncMock(return_value={"results": [1, 2, 3]})

        manager = ConversationManager(
            engine=mock_engine,
            tool_executor=mock_executor,
        )
        return manager

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, manager):
        """Test successful tool execution."""
        tool_call = ToolCall(
            id="call_1",
            name="search",
            arguments={"query": "VMs"},
        )

        result = await manager._execute_tool(tool_call)

        assert result.success is True
        assert result.data == {"results": [1, 2, 3]}
        manager.tool_executor.assert_called_once_with("search", {"query": "VMs"})

    @pytest.mark.asyncio
    async def test_execute_tool_error(self, manager):
        """Test tool execution error handling."""
        manager.tool_executor.side_effect = Exception("Tool failed")

        tool_call = ToolCall(id="call_1", name="search", arguments={})

        result = await manager._execute_tool(tool_call)

        assert result.success is False
        assert "Tool failed" in result.error


class TestSummarizeResult:
    """Tests for result summarization."""

    @pytest.fixture
    def manager(self):
        """Create manager for testing."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        return ConversationManager(engine=mock_engine)

    def test_summarize_error_result(self, manager):
        """Test summarizing error result."""
        result = ToolResult(
            tool_call_id="1",
            name="search",
            success=False,
            error="Not found",
        )

        summary = manager._summarize_result(result)
        assert "Error: Not found" in summary

    def test_summarize_results_list(self, manager):
        """Test summarizing results with list."""
        result = ToolResult(
            tool_call_id="1",
            name="search",
            success=True,
            data={"results": [1, 2, 3, 4, 5]},
        )

        summary = manager._summarize_result(result)
        assert "5 results" in summary

    def test_summarize_total_count(self, manager):
        """Test summarizing with total_count."""
        result = ToolResult(
            tool_call_id="1",
            name="search",
            success=True,
            data={"total_count": 42},
        )

        summary = manager._summarize_result(result)
        assert "42 items" in summary

    def test_summarize_generic_success(self, manager):
        """Test summarizing generic success."""
        result = ToolResult(
            tool_call_id="1",
            name="search",
            success=True,
            data="some data",
        )

        summary = manager._summarize_result(result)
        assert "successfully" in summary.lower()


class TestExtractSources:
    """Tests for source extraction."""

    @pytest.fixture
    def manager(self):
        """Create manager for testing."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        return ConversationManager(engine=mock_engine)

    def test_extract_azure_resource_sources(self, manager):
        """Test extracting Azure resource sources."""
        data = {
            "results": [
                {"resource_id": "/sub/123/vm/1", "name": "vm-1"},
                {"resource_id": "/sub/123/vm/2", "name": "vm-2"},
            ]
        }

        sources = manager._extract_sources(data)

        assert len(sources) == 2
        assert sources[0]["type"] == "azure_resource"
        assert sources[0]["id"] == "/sub/123/vm/1"

    def test_extract_terraform_sources(self, manager):
        """Test extracting Terraform sources."""
        data = {
            "results": [
                {"address": "azurerm_vm.main", "file_path": "main.tf"},
            ]
        }

        sources = manager._extract_sources(data)

        assert len(sources) == 1
        assert sources[0]["type"] == "terraform"
        assert sources[0]["address"] == "azurerm_vm.main"

    def test_extract_git_sources(self, manager):
        """Test extracting Git sources."""
        data = {
            "results": [
                {"sha": "abc123def456", "message": "Update configuration"},
            ]
        }

        sources = manager._extract_sources(data)

        assert len(sources) == 1
        assert sources[0]["type"] == "git_commit"
        assert sources[0]["sha"] == "abc123de"  # Short SHA

    def test_extract_sources_limit(self, manager):
        """Test that sources are limited to 5."""
        data = {
            "results": [
                {"resource_id": f"/vm/{i}"} for i in range(10)
            ]
        }

        sources = manager._extract_sources(data)

        assert len(sources) == 5

    def test_extract_sources_empty(self, manager):
        """Test extracting from empty data."""
        sources = manager._extract_sources({})
        assert sources == []

        sources = manager._extract_sources({"results": []})
        assert sources == []


class TestConversationHistory:
    """Tests for conversation history methods."""

    @pytest.fixture
    def manager(self):
        """Create manager with conversations."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        manager = ConversationManager(engine=mock_engine)

        # Create some conversations
        conv1 = manager.create_conversation(
            conversation_id="conv-1",
            user_context={"user_id": "user-1"},
        )
        conv1.add_message(Message(role=MessageRole.USER, content="Hello"))
        conv1.add_message(Message(role=MessageRole.ASSISTANT, content="Hi there"))

        conv2 = manager.create_conversation(
            conversation_id="conv-2",
            user_context={"user_id": "user-2"},
        )

        return manager

    def test_get_conversation_history(self, manager):
        """Test getting conversation history."""
        history = manager.get_conversation_history("conv-1")

        assert history is not None
        assert len(history) == 2  # Excludes system message
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"

    def test_get_conversation_history_not_found(self, manager):
        """Test getting history for non-existent conversation."""
        history = manager.get_conversation_history("fake")
        assert history is None

    def test_list_conversations(self, manager):
        """Test listing all conversations."""
        convs = manager.list_conversations()

        assert len(convs) == 2
        # Should be sorted by updated_at descending
        assert "id" in convs[0]
        assert "preview" in convs[0]

    def test_list_conversations_by_user(self, manager):
        """Test listing conversations for specific user."""
        convs = manager.list_conversations(user_id="user-1")

        assert len(convs) == 1
        assert convs[0]["id"] == "conv-1"


class TestContextManagement:
    """Tests for context management."""

    @pytest.fixture
    def manager(self):
        """Create manager for testing."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()

        async def mock_chat(*args, **kwargs):
            yield StreamChunk(content="Summary of conversation")
            yield StreamChunk(finish_reason="stop")

        mock_engine.chat = mock_chat

        manager = ConversationManager(engine=mock_engine)
        manager.MAX_CONTEXT_MESSAGES = 5  # Lower for testing
        return manager

    @pytest.mark.asyncio
    async def test_get_context_messages_short(self, manager):
        """Test getting context for short conversation."""
        conv = manager.create_conversation()
        conv.add_message(Message(role=MessageRole.USER, content="Hello"))

        messages = await manager._get_context_messages(conv)

        # Should return all messages
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_get_context_messages_long(self, manager):
        """Test getting context for long conversation with summarization."""
        conv = manager.create_conversation()

        # Add many messages
        for i in range(10):
            conv.add_message(Message(role=MessageRole.USER, content=f"Message {i}"))
            conv.add_message(Message(role=MessageRole.ASSISTANT, content=f"Reply {i}"))

        messages = await manager._get_context_messages(conv)

        # Should be summarized to fit MAX_CONTEXT_MESSAGES
        assert len(messages) <= manager.MAX_CONTEXT_MESSAGES


class TestLoadConversation:
    """Tests for loading conversations from memory store."""

    @pytest.fixture
    def manager(self):
        """Create manager with mock memory store."""
        from src.orchestration.conversation import ConversationManager
        mock_engine = AsyncMock()
        mock_memory = AsyncMock()

        manager = ConversationManager(
            engine=mock_engine,
            memory_store=mock_memory,
        )
        return manager

    @pytest.mark.asyncio
    async def test_load_from_memory(self, manager):
        """Test loading conversation from memory store."""
        # Create a conversation to return
        loaded_conv = Conversation(id="loaded-conv")
        loaded_conv.add_message(Message(role=MessageRole.USER, content="Hello"))
        manager.memory_store.load_conversation.return_value = loaded_conv

        conv = await manager.load_conversation("loaded-conv")

        assert conv is not None
        assert conv.id == "loaded-conv"
        assert "loaded-conv" in manager.conversations

    @pytest.mark.asyncio
    async def test_load_from_cache(self, manager):
        """Test loading from in-memory cache."""
        # Create conversation in cache
        manager.create_conversation(conversation_id="cached-conv")

        conv = await manager.load_conversation("cached-conv")

        assert conv is not None
        assert conv.id == "cached-conv"
        # Should not call memory store
        manager.memory_store.load_conversation.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_not_found(self, manager):
        """Test loading non-existent conversation."""
        manager.memory_store.load_conversation.return_value = None

        conv = await manager.load_conversation("not-found")

        assert conv is None
