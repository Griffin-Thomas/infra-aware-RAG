"""Unit tests for MemoryStore."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.orchestration.memory import MemoryStore
from src.orchestration.models import Conversation, Message, MessageRole


class TestMemoryStoreInit:
    """Tests for MemoryStore initialization."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com"
        )

        assert store.cosmos_endpoint == "https://test.documents.azure.com"
        assert store.database_name == "infra-rag"
        assert store.container_name == "conversations"
        assert store._initialized is False

    def test_init_custom_names(self):
        """Test initialization with custom names."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            database_name="my-db",
            container_name="my-container",
        )

        assert store.database_name == "my-db"
        assert store.container_name == "my-container"


class TestMemoryStoreInit2:
    """Tests for MemoryStore.init() method."""

    @pytest.mark.asyncio
    async def test_init_with_credential(self):
        """Test initialization with provided credential."""
        mock_credential = MagicMock()

        with patch("src.orchestration.memory.CosmosClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            store = MemoryStore(
                cosmos_endpoint="https://test.documents.azure.com",
                credential=mock_credential,
            )
            await store.init()

            mock_client_class.assert_called_once_with(
                "https://test.documents.azure.com",
                mock_credential,
            )
            assert store._initialized is True

    @pytest.mark.asyncio
    async def test_init_idempotent(self):
        """Test that init can be called multiple times."""
        with patch("src.orchestration.memory.CosmosClient") as mock_client_class:
            mock_client_class.return_value = AsyncMock()

            store = MemoryStore(
                cosmos_endpoint="https://test.documents.azure.com",
                credential=MagicMock(),
            )
            await store.init()
            await store.init()  # Should not fail

            # Should only create client once
            assert mock_client_class.call_count == 1


class TestSaveConversation:
    """Tests for saving conversations."""

    @pytest.fixture
    def mock_store(self):
        """Create store with mocked client."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            credential=MagicMock(),
        )

        # Mock the client
        mock_container = AsyncMock()
        mock_db = MagicMock()
        mock_db.get_container_client.return_value = mock_container
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_db

        store._client = mock_client
        store._initialized = True

        return store, mock_container

    @pytest.mark.asyncio
    async def test_save_conversation_basic(self, mock_store):
        """Test saving a basic conversation."""
        store, mock_container = mock_store

        conv = Conversation(id="test-conv")
        conv.add_message(Message(role=MessageRole.USER, content="Hello"))

        await store.save_conversation(conv)

        mock_container.upsert_item.assert_called_once()
        saved_doc = mock_container.upsert_item.call_args[0][0]

        assert saved_doc["id"] == "test-conv"
        assert saved_doc["type"] == "conversation"
        assert len(saved_doc["messages"]) == 1

    @pytest.mark.asyncio
    async def test_save_conversation_with_metadata(self, mock_store):
        """Test saving conversation with metadata."""
        store, mock_container = mock_store

        conv = Conversation(
            id="test-conv",
            metadata={"user_id": "user-123"},
        )

        await store.save_conversation(conv)

        saved_doc = mock_container.upsert_item.call_args[0][0]
        assert saved_doc["metadata"]["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_save_conversation_ttl(self, mock_store):
        """Test that TTL is set."""
        store, mock_container = mock_store

        conv = Conversation(id="test-conv")
        await store.save_conversation(conv)

        saved_doc = mock_container.upsert_item.call_args[0][0]
        assert saved_doc["ttl"] == 86400 * 30  # 30 days

    @pytest.mark.asyncio
    async def test_save_not_initialized(self):
        """Test saving without initialization raises error."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
        )

        conv = Conversation(id="test")

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.save_conversation(conv)


class TestLoadConversation:
    """Tests for loading conversations."""

    @pytest.fixture
    def mock_store(self):
        """Create store with mocked client."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            credential=MagicMock(),
        )

        mock_container = AsyncMock()
        mock_db = MagicMock()
        mock_db.get_container_client.return_value = mock_container
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_db

        store._client = mock_client
        store._initialized = True

        return store, mock_container

    @pytest.mark.asyncio
    async def test_load_conversation_found(self, mock_store):
        """Test loading existing conversation."""
        store, mock_container = mock_store

        now = datetime.utcnow()
        mock_container.read_item = AsyncMock(return_value={
            "id": "test-conv",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "metadata": {"user_id": "user-1"},
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": now.isoformat(),
                },
                {
                    "role": "assistant",
                    "content": "Hi there",
                    "timestamp": now.isoformat(),
                },
            ],
        })

        conv = await store.load_conversation("test-conv")

        assert conv is not None
        assert conv.id == "test-conv"
        assert len(conv.messages) == 2
        assert conv.messages[0].role == MessageRole.USER

    @pytest.mark.asyncio
    async def test_load_conversation_not_found(self, mock_store):
        """Test loading non-existent conversation."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        store, mock_container = mock_store
        mock_container.read_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(message="Not found", status_code=404)
        )

        conv = await store.load_conversation("not-found")

        assert conv is None


class TestDeleteConversation:
    """Tests for deleting conversations."""

    @pytest.fixture
    def mock_store(self):
        """Create store with mocked client."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            credential=MagicMock(),
        )

        mock_container = AsyncMock()
        mock_db = MagicMock()
        mock_db.get_container_client.return_value = mock_container
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_db

        store._client = mock_client
        store._initialized = True

        return store, mock_container

    @pytest.mark.asyncio
    async def test_delete_conversation_found(self, mock_store):
        """Test deleting existing conversation."""
        store, mock_container = mock_store

        result = await store.delete_conversation("test-conv")

        assert result is True
        mock_container.delete_item.assert_called_once_with(
            "test-conv",
            partition_key="test-conv",
        )

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, mock_store):
        """Test deleting non-existent conversation."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        store, mock_container = mock_store
        mock_container.delete_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(message="Not found", status_code=404)
        )

        result = await store.delete_conversation("not-found")

        assert result is False


class TestUserConversations:
    """Tests for getting user conversations."""

    @pytest.fixture
    def mock_store(self):
        """Create store with mocked client."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            credential=MagicMock(),
        )

        mock_container = AsyncMock()
        mock_db = MagicMock()
        mock_db.get_container_client.return_value = mock_container
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_db

        store._client = mock_client
        store._initialized = True

        return store, mock_container

    @pytest.mark.asyncio
    async def test_get_user_conversations(self, mock_store):
        """Test getting user's conversations."""
        store, mock_container = mock_store

        # Mock async iterator
        async def mock_query_items(*args, **kwargs):
            items = [
                {"id": "conv-1", "message_count": 5},
                {"id": "conv-2", "message_count": 3},
            ]
            for item in items:
                yield item

        mock_container.query_items = mock_query_items

        results = await store.get_user_conversations("user-123", limit=10)

        assert len(results) == 2
        assert results[0]["id"] == "conv-1"


class TestUserPreferences:
    """Tests for user preferences."""

    @pytest.fixture
    def mock_store(self):
        """Create store with mocked client."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            credential=MagicMock(),
        )

        mock_container = AsyncMock()
        mock_db = MagicMock()
        mock_db.get_container_client.return_value = mock_container
        mock_client = MagicMock()
        mock_client.get_database_client.return_value = mock_db

        store._client = mock_client
        store._initialized = True

        return store, mock_container

    @pytest.mark.asyncio
    async def test_save_user_preference(self, mock_store):
        """Test saving a user preference."""
        store, mock_container = mock_store

        await store.save_user_preference(
            user_id="user-123",
            key="theme",
            value="dark",
        )

        mock_container.upsert_item.assert_called_once()
        saved_doc = mock_container.upsert_item.call_args[0][0]

        assert saved_doc["id"] == "pref:user-123:theme"
        assert saved_doc["type"] == "preference"
        assert saved_doc["value"] == "dark"

    @pytest.mark.asyncio
    async def test_get_user_preference_found(self, mock_store):
        """Test getting existing preference."""
        store, mock_container = mock_store
        mock_container.read_item = AsyncMock(return_value={
            "value": "dark"
        })

        value = await store.get_user_preference("user-123", "theme")

        assert value == "dark"

    @pytest.mark.asyncio
    async def test_get_user_preference_not_found(self, mock_store):
        """Test getting non-existent preference."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        store, mock_container = mock_store
        mock_container.read_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(message="Not found", status_code=404)
        )

        value = await store.get_user_preference("user-123", "missing")

        assert value is None

    @pytest.mark.asyncio
    async def test_get_all_user_preferences(self, mock_store):
        """Test getting all user preferences."""
        store, mock_container = mock_store

        async def mock_query_items(*args, **kwargs):
            items = [
                {"key": "theme", "value": "dark"},
                {"key": "language", "value": "en"},
            ]
            for item in items:
                yield item

        mock_container.query_items = mock_query_items

        prefs = await store.get_user_preferences("user-123")

        assert prefs["theme"] == "dark"
        assert prefs["language"] == "en"

    @pytest.mark.asyncio
    async def test_delete_user_preference_found(self, mock_store):
        """Test deleting existing preference."""
        store, mock_container = mock_store

        result = await store.delete_user_preference("user-123", "theme")

        assert result is True
        mock_container.delete_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_user_preference_not_found(self, mock_store):
        """Test deleting non-existent preference."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        store, mock_container = mock_store
        mock_container.delete_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(message="Not found", status_code=404)
        )

        result = await store.delete_user_preference("user-123", "missing")

        assert result is False


class TestMemoryStoreClose:
    """Tests for closing memory store."""

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the store."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
            credential=MagicMock(),
        )

        mock_client = AsyncMock()
        store._client = mock_client
        store._initialized = True

        await store.close()

        mock_client.close.assert_called_once()
        assert store._client is None
        assert store._initialized is False

    @pytest.mark.asyncio
    async def test_close_not_initialized(self):
        """Test closing uninitialized store."""
        store = MemoryStore(
            cosmos_endpoint="https://test.documents.azure.com",
        )

        # Should not raise
        await store.close()
