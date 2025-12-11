"""Persistent memory store for conversation history.

This module provides the MemoryStore class for persisting conversations
and user preferences to Cosmos DB.
"""

import logging
from datetime import datetime
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from .models import Conversation, Message, MessageRole

logger = logging.getLogger(__name__)


class MemoryStore:
    """Persistent storage for conversation memory.

    Stores:
    - Full conversation history
    - User preferences
    - Frequently accessed resources (for faster retrieval)

    Uses Cosmos DB NoSQL API for storage with automatic TTL
    for conversation expiration.

    Example:
        store = MemoryStore(
            cosmos_endpoint="https://myaccount.documents.azure.com",
            database_name="infra-rag",
        )
        await store.init()

        await store.save_conversation(conversation)
        loaded = await store.load_conversation(conversation.id)

        await store.close()
    """

    DEFAULT_DATABASE = "infra-rag"
    DEFAULT_CONVERSATIONS_CONTAINER = "conversations"
    DEFAULT_TTL_DAYS = 30

    def __init__(
        self,
        cosmos_endpoint: str,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: Any | None = None,
    ):
        """Initialize the memory store.

        Args:
            cosmos_endpoint: Cosmos DB account endpoint
            database_name: Database name (default: infra-rag)
            container_name: Container name (default: conversations)
            credential: Optional Azure credential (uses DefaultAzureCredential if None)
        """
        self.cosmos_endpoint = cosmos_endpoint
        self.database_name = database_name or self.DEFAULT_DATABASE
        self.container_name = container_name or self.DEFAULT_CONVERSATIONS_CONTAINER
        self._credential = credential
        self._client: CosmosClient | None = None
        self._initialized = False

    async def init(self) -> None:
        """Initialize Cosmos DB connection.

        Must be called before using any other methods.
        """
        if self._initialized:
            return

        if self._credential:
            self._client = CosmosClient(self.cosmos_endpoint, self._credential)
        else:
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            self._client = CosmosClient(self.cosmos_endpoint, credential)

        self._initialized = True
        logger.info(f"MemoryStore initialized with database: {self.database_name}")

    def _ensure_initialized(self) -> None:
        """Ensure the store is initialized."""
        if not self._initialized or not self._client:
            raise RuntimeError("MemoryStore not initialized. Call init() first.")

    async def save_conversation(self, conversation: Conversation) -> None:
        """Save conversation to Cosmos DB.

        Args:
            conversation: The conversation to save

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        # Build document
        doc = {
            "id": conversation.id,
            "type": "conversation",
            "partition_key": conversation.id,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "metadata": conversation.metadata,
            "messages": [
                {
                    "role": m.role.value,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "tool_calls": m.tool_calls,
                    "tool_call_id": m.tool_call_id,
                    "name": m.name,
                }
                for m in conversation.messages
            ],
            "ttl": 86400 * self.DEFAULT_TTL_DAYS,  # 30 day retention
        }

        await container.upsert_item(doc)
        logger.debug(f"Saved conversation {conversation.id}")

    async def load_conversation(self, conversation_id: str) -> Conversation | None:
        """Load conversation from Cosmos DB.

        Args:
            conversation_id: The conversation ID

        Returns:
            The Conversation if found, None otherwise

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        try:
            doc = await container.read_item(
                conversation_id, partition_key=conversation_id
            )

            conv = Conversation(
                id=doc["id"],
                created_at=datetime.fromisoformat(doc["created_at"]),
                updated_at=datetime.fromisoformat(doc["updated_at"]),
                metadata=doc.get("metadata", {}),
            )

            for m in doc.get("messages", []):
                msg = Message(
                    role=MessageRole(m["role"]),
                    content=m["content"],
                    timestamp=datetime.fromisoformat(m["timestamp"])
                    if m.get("timestamp")
                    else datetime.utcnow(),
                    tool_calls=m.get("tool_calls"),
                    tool_call_id=m.get("tool_call_id"),
                    name=m.get("name"),
                )
                conv.messages.append(msg)

            logger.debug(f"Loaded conversation {conversation_id}")
            return conv

        except CosmosResourceNotFoundError:
            logger.debug(f"Conversation {conversation_id} not found")
            return None

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation from Cosmos DB.

        Args:
            conversation_id: The conversation ID

        Returns:
            True if deleted, False if not found

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        try:
            await container.delete_item(conversation_id, partition_key=conversation_id)
            logger.info(f"Deleted conversation {conversation_id}")
            return True
        except CosmosResourceNotFoundError:
            return False

    async def get_user_conversations(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent conversations for a user.

        Args:
            user_id: The user ID
            limit: Maximum number of conversations to return

        Returns:
            List of conversation summary dicts

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        query = """
        SELECT c.id, c.created_at, c.updated_at, c.metadata,
               ARRAY_LENGTH(c.messages) as message_count
        FROM c
        WHERE c.type = 'conversation'
        AND c.metadata.user_id = @user_id
        ORDER BY c.updated_at DESC
        OFFSET 0 LIMIT @limit
        """

        results: list[dict[str, Any]] = []
        async for item in container.query_items(
            query,
            parameters=[
                {"name": "@user_id", "value": user_id},
                {"name": "@limit", "value": limit},
            ],
        ):
            results.append(item)

        return results

    async def save_user_preference(
        self, user_id: str, key: str, value: Any
    ) -> None:
        """Save a user preference.

        Args:
            user_id: The user ID
            key: Preference key
            value: Preference value

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        doc_id = f"pref:{user_id}:{key}"
        doc = {
            "id": doc_id,
            "partition_key": doc_id,
            "type": "preference",
            "user_id": user_id,
            "key": key,
            "value": value,
            "updated_at": datetime.utcnow().isoformat(),
        }

        await container.upsert_item(doc)
        logger.debug(f"Saved preference {key} for user {user_id}")

    async def get_user_preference(
        self, user_id: str, key: str
    ) -> Any | None:
        """Get a specific user preference.

        Args:
            user_id: The user ID
            key: Preference key

        Returns:
            The preference value if found, None otherwise

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        doc_id = f"pref:{user_id}:{key}"
        try:
            doc = await container.read_item(doc_id, partition_key=doc_id)
            return doc.get("value")
        except CosmosResourceNotFoundError:
            return None

    async def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Get all preferences for a user.

        Args:
            user_id: The user ID

        Returns:
            Dict of preference key -> value

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        query = """
        SELECT c.key, c.value
        FROM c
        WHERE c.type = 'preference'
        AND c.user_id = @user_id
        """

        prefs: dict[str, Any] = {}
        async for item in container.query_items(
            query,
            parameters=[{"name": "@user_id", "value": user_id}],
        ):
            prefs[item["key"]] = item["value"]

        return prefs

    async def delete_user_preference(self, user_id: str, key: str) -> bool:
        """Delete a user preference.

        Args:
            user_id: The user ID
            key: Preference key

        Returns:
            True if deleted, False if not found

        Raises:
            RuntimeError: If store not initialized
        """
        self._ensure_initialized()
        assert self._client is not None

        db = self._client.get_database_client(self.database_name)
        container = db.get_container_client(self.container_name)

        doc_id = f"pref:{user_id}:{key}"
        try:
            await container.delete_item(doc_id, partition_key=doc_id)
            return True
        except CosmosResourceNotFoundError:
            return False

    async def close(self) -> None:
        """Close Cosmos DB connection."""
        if self._client:
            await self._client.close()
            self._client = None
            self._initialized = False
            logger.info("MemoryStore closed")
