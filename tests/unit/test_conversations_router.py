"""Unit tests for conversations router."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.api.models.conversation import (
    ConversationResponse,
    MessageResponse,
)
from src.orchestration.models import AssistantResponse, Conversation, Message, MessageRole


# Mock the tool definitions import before importing the router
@pytest.fixture(autouse=True)
def mock_tool_definitions():
    """Mock TOOL_DEFINITIONS for all tests."""
    with patch.dict(
        "sys.modules",
        {"src.api.tools.definitions": MagicMock(TOOL_DEFINITIONS=[])}
    ):
        import importlib
        import src.orchestration.conversation
        importlib.reload(src.orchestration.conversation)
        yield
        importlib.reload(src.orchestration.conversation)


@pytest.fixture
def mock_conversation_manager():
    """Create a mock conversation manager."""
    manager = MagicMock()

    # Create a sample conversation
    conv = Conversation(id="test-conv-123")
    conv.metadata = {"user_id": "anonymous"}
    conv.add_message(Message(role=MessageRole.SYSTEM, content="System prompt"))
    conv.add_message(Message(role=MessageRole.USER, content="Hello"))
    conv.add_message(Message(role=MessageRole.ASSISTANT, content="Hi there!"))

    manager.create_conversation.return_value = conv
    manager.get_conversation.return_value = conv
    manager.load_conversation = AsyncMock(return_value=conv)
    manager.delete_conversation.return_value = True
    manager.get_conversation_history.return_value = [
        {"role": "user", "content": "Hello", "timestamp": datetime.utcnow().isoformat()},
        {"role": "assistant", "content": "Hi there!", "timestamp": datetime.utcnow().isoformat()},
    ]
    manager.list_conversations.return_value = [
        {
            "id": "conv-1",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "message_count": 2,
            "metadata": {"user_id": "anonymous"},
        }
    ]

    return manager


@pytest.fixture
def mock_current_user():
    """Create a mock current user."""
    return {
        "sub": "anonymous",
        "oid": "anonymous",
        "name": "Test User",
    }


@pytest.fixture
def app(mock_conversation_manager, mock_current_user):
    """Create test FastAPI app with mocked dependencies."""
    from src.api.routers.conversations import router

    app = FastAPI()
    app.include_router(router)

    # Override dependencies
    app.dependency_overrides = {
        get_conversation_manager: lambda: mock_conversation_manager,
        get_current_user: lambda: mock_current_user,
    }

    return app


# Import dependencies after mock setup
from src.api.dependencies import get_conversation_manager, get_current_user


class TestCreateConversation:
    """Tests for POST /conversations."""

    def test_create_conversation(self, app, mock_conversation_manager):
        """Test creating a new conversation."""
        client = TestClient(app)

        response = client.post("/conversations", json={})

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["id"] == "test-conv-123"
        mock_conversation_manager.create_conversation.assert_called_once()

    def test_create_conversation_with_metadata(self, app, mock_conversation_manager):
        """Test creating conversation with metadata."""
        client = TestClient(app)

        response = client.post(
            "/conversations",
            json={"metadata": {"custom_field": "value"}},
        )

        assert response.status_code == 201


class TestListConversations:
    """Tests for GET /conversations."""

    def test_list_conversations(self, app, mock_conversation_manager):
        """Test listing conversations."""
        client = TestClient(app)

        response = client.get("/conversations")

        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert "total_count" in data
        assert len(data["conversations"]) == 1

    def test_list_conversations_with_limit(self, app, mock_conversation_manager):
        """Test listing with limit parameter."""
        client = TestClient(app)

        response = client.get("/conversations?limit=5")

        assert response.status_code == 200


class TestGetConversation:
    """Tests for GET /conversations/{id}."""

    def test_get_conversation(self, app, mock_conversation_manager):
        """Test getting a specific conversation."""
        client = TestClient(app)

        response = client.get("/conversations/test-conv-123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-conv-123"

    def test_get_conversation_not_found(self, app, mock_conversation_manager):
        """Test getting non-existent conversation."""
        mock_conversation_manager.get_conversation.return_value = None
        mock_conversation_manager.load_conversation.return_value = None

        client = TestClient(app)

        response = client.get("/conversations/not-found")

        assert response.status_code == 404


class TestDeleteConversation:
    """Tests for DELETE /conversations/{id}."""

    def test_delete_conversation(self, app, mock_conversation_manager):
        """Test deleting a conversation."""
        client = TestClient(app)

        response = client.delete("/conversations/test-conv-123")

        assert response.status_code == 204
        mock_conversation_manager.delete_conversation.assert_called_once_with("test-conv-123")

    def test_delete_conversation_not_found(self, app, mock_conversation_manager):
        """Test deleting non-existent conversation."""
        mock_conversation_manager.get_conversation.return_value = None
        mock_conversation_manager.delete_conversation.return_value = False

        client = TestClient(app)

        response = client.delete("/conversations/not-found")

        assert response.status_code == 404


class TestGetHistory:
    """Tests for GET /conversations/{id}/history."""

    def test_get_history(self, app, mock_conversation_manager):
        """Test getting conversation history."""
        client = TestClient(app)

        response = client.get("/conversations/test-conv-123/history")

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "test-conv-123"
        assert "messages" in data
        assert len(data["messages"]) == 2

    def test_get_history_not_found(self, app, mock_conversation_manager):
        """Test getting history for non-existent conversation."""
        mock_conversation_manager.get_conversation.return_value = None
        mock_conversation_manager.load_conversation.return_value = None

        client = TestClient(app)

        response = client.get("/conversations/not-found/history")

        assert response.status_code == 404


class TestSendMessage:
    """Tests for POST /conversations/{id}/messages."""

    @pytest.mark.asyncio
    async def test_send_message_non_streaming(self, app, mock_conversation_manager):
        """Test sending a message without streaming."""
        # Mock send_message to return an AssistantResponse
        async def mock_send_message(conv_id, content, stream=True):
            yield AssistantResponse(
                content="Hello! How can I help?",
                tool_calls_made=[],
                sources=[],
                tokens_used=50,
            )

        mock_conversation_manager.send_message = mock_send_message

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/conversations/test-conv-123/messages",
                json={"content": "Hello", "stream": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["content"] == "Hello! How can I help?"

    def test_send_message_conversation_not_found(self, app, mock_conversation_manager):
        """Test sending message to non-existent conversation."""
        mock_conversation_manager.get_conversation.return_value = None
        mock_conversation_manager.load_conversation = AsyncMock(return_value=None)

        client = TestClient(app)

        response = client.post(
            "/conversations/not-found/messages",
            json={"content": "Hello", "stream": False},
        )

        assert response.status_code == 404

    def test_send_message_empty_content(self, app):
        """Test sending message with empty content."""
        client = TestClient(app)

        response = client.post(
            "/conversations/test-conv-123/messages",
            json={"content": "", "stream": False},
        )

        # Should fail validation (min_length=1)
        assert response.status_code == 422


class TestConversationModels:
    """Tests for conversation API models."""

    def test_conversation_response_model(self):
        """Test ConversationResponse model."""
        response = ConversationResponse(
            id="test-123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            message_count=5,
            metadata={"user_id": "user-1"},
        )

        assert response.id == "test-123"
        assert response.message_count == 5

    def test_message_response_model(self):
        """Test MessageResponse model."""
        response = MessageResponse(
            content="Hello!",
            tool_calls_made=[],
            sources=[],
            tokens_used=50,
        )

        assert response.content == "Hello!"
        assert response.tokens_used == 50


class TestAuthorizationChecks:
    """Tests for authorization checks."""

    def test_get_other_users_conversation(self, app, mock_conversation_manager):
        """Test that users can't access others' conversations."""
        # Create conversation with different user
        conv = Conversation(id="other-user-conv")
        conv.metadata = {"user_id": "other-user-123"}
        mock_conversation_manager.get_conversation.return_value = conv

        client = TestClient(app)

        response = client.get("/conversations/other-user-conv")

        assert response.status_code == 403

    def test_delete_other_users_conversation(self, app, mock_conversation_manager):
        """Test that users can't delete others' conversations."""
        conv = Conversation(id="other-user-conv")
        conv.metadata = {"user_id": "other-user-123"}
        mock_conversation_manager.get_conversation.return_value = conv

        client = TestClient(app)

        response = client.delete("/conversations/other-user-conv")

        assert response.status_code == 403
