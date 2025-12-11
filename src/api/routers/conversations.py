"""Conversation API router for chat interactions.

This module provides endpoints for managing conversations and sending
messages to the infra-aware assistant.
"""

import json
import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, Response

from src.api.dependencies import (
    get_conversation_manager,
    get_current_user,
)
from src.api.models.conversation import (
    ConversationHistoryResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageHistoryItem,
    MessageRequest,
    MessageResponse,
    SourceReference,
    StreamEvent,
    ToolCallInfo,
)
from src.orchestration.conversation import ConversationManager
from src.orchestration.models import AssistantResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    request: CreateConversationRequest | None = None,
    manager: ConversationManager = Depends(get_conversation_manager),
    user: dict[str, Any] = Depends(get_current_user),
) -> ConversationResponse:
    """
    Create a new conversation.

    Creates a new conversation session with the infra-aware assistant.
    The conversation is initialized with a system prompt that provides
    context about the user's Azure environment.

    Returns the conversation ID which should be used for subsequent
    message requests.
    """
    # Build user context
    user_context: dict[str, Any] = {
        "user_id": user.get("sub") or user.get("oid") or "anonymous",
        "user_name": user.get("name") or user.get("preferred_username"),
    }

    # Add any metadata from request
    if request and request.metadata:
        user_context.update(request.metadata)

    logger.info(f"Creating conversation for user {user_context.get('user_id')}")

    conversation = manager.create_conversation(user_context=user_context)

    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages) - 1,  # Exclude system prompt
        metadata=conversation.metadata,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = 20,
    manager: ConversationManager = Depends(get_conversation_manager),
    user: dict[str, Any] = Depends(get_current_user),
) -> ConversationListResponse:
    """
    List conversations for the current user.

    Returns a list of conversation summaries, ordered by most recently
    updated first. Use the conversation ID to retrieve full history
    or continue the conversation.
    """
    user_id = user.get("sub") or user.get("oid")

    conversations = manager.list_conversations(user_id=user_id)

    # Apply limit
    conversations = conversations[:limit]

    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                id=conv["id"],
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
                message_count=conv["message_count"],
                metadata=conv.get("metadata", {}),
            )
            for conv in conversations
        ],
        total_count=len(conversations),
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    manager: ConversationManager = Depends(get_conversation_manager),
    user: dict[str, Any] = Depends(get_current_user),
) -> ConversationResponse:
    """
    Get details for a specific conversation.

    Returns the conversation metadata and message count.
    """
    conversation = manager.get_conversation(conversation_id)

    if not conversation:
        # Try loading from memory store
        conversation = await manager.load_conversation(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )

    # Verify ownership
    user_id = user.get("sub") or user.get("oid")
    if conversation.user_id and conversation.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this conversation",
        )

    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages) - 1,
        metadata=conversation.metadata,
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    manager: ConversationManager = Depends(get_conversation_manager),
    user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    """
    Delete a conversation.

    Permanently deletes the conversation and all its messages.
    """
    conversation = manager.get_conversation(conversation_id)

    if conversation:
        # Verify ownership
        user_id = user.get("sub") or user.get("oid")
        if conversation.user_id and conversation.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to delete this conversation",
            )

    deleted = manager.delete_conversation(conversation_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )

    return Response(status_code=204)


@router.get(
    "/{conversation_id}/history",
    response_model=ConversationHistoryResponse,
)
async def get_conversation_history(
    conversation_id: str,
    manager: ConversationManager = Depends(get_conversation_manager),
    user: dict[str, Any] = Depends(get_current_user),
) -> ConversationHistoryResponse:
    """
    Get the message history for a conversation.

    Returns all messages in the conversation (excluding system messages).
    """
    conversation = manager.get_conversation(conversation_id)

    if not conversation:
        conversation = await manager.load_conversation(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )

    # Verify ownership
    user_id = user.get("sub") or user.get("oid")
    if conversation.user_id and conversation.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this conversation",
        )

    history = manager.get_conversation_history(conversation_id)

    if history is None:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=[
            MessageHistoryItem(
                role=msg["role"],
                content=msg["content"],
                timestamp=msg["timestamp"],
            )
            for msg in history
        ],
    )


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: MessageRequest,
    manager: ConversationManager = Depends(get_conversation_manager),
    user: dict[str, Any] = Depends(get_current_user),
):
    """
    Send a message in a conversation.

    Sends a user message and returns the assistant's response.

    By default, responses are streamed using Server-Sent Events (SSE).
    Set `stream=false` to receive the complete response at once.

    **Streaming Response Format:**

    The response is a stream of SSE events:
    - `data: {"type": "token", "content": "..."}` - Token chunks
    - `data: {"type": "tool_call", "tool_call": {...}}` - Tool execution
    - `data: {"type": "complete", "response": {...}}` - Final response
    - `data: {"type": "error", "message": "..."}` - Error occurred
    """
    # Verify conversation exists
    conversation = manager.get_conversation(conversation_id)

    if not conversation:
        conversation = await manager.load_conversation(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )

    # Verify ownership
    user_id = user.get("sub") or user.get("oid")
    if conversation.user_id and conversation.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this conversation",
        )

    logger.info(
        f"Message in conversation {conversation_id}: "
        f"'{request.content[:50]}...' (stream={request.stream})"
    )

    if request.stream:
        return StreamingResponse(
            _stream_response(manager, conversation_id, request.content),
            media_type="text/event-stream",
        )
    else:
        # Non-streaming response
        final_response: AssistantResponse | None = None

        async for response in manager.send_message(
            conversation_id,
            request.content,
            stream=False,
        ):
            if isinstance(response, AssistantResponse):
                final_response = response

        if not final_response:
            raise HTTPException(
                status_code=500,
                detail="No response generated",
            )

        return MessageResponse(
            content=final_response.content,
            tool_calls_made=[
                ToolCallInfo(
                    name=tc["name"],
                    arguments=tc["arguments"],
                    result_summary=tc.get("result_summary"),
                )
                for tc in final_response.tool_calls_made
            ],
            sources=[
                SourceReference(**src)
                for src in final_response.sources
            ],
            tokens_used=final_response.tokens_used,
        )


async def _stream_response(
    manager: ConversationManager,
    conversation_id: str,
    content: str,
) -> AsyncGenerator[str, None]:
    """Stream response as SSE events."""
    try:
        async for response in manager.send_message(
            conversation_id,
            content,
            stream=True,
        ):
            if isinstance(response, str):
                # Token chunk
                event = StreamEvent(type="token", content=response)
                yield f"data: {event.model_dump_json()}\n\n"

            elif isinstance(response, AssistantResponse):
                # Final response
                message_response = MessageResponse(
                    content=response.content,
                    tool_calls_made=[
                        ToolCallInfo(
                            name=tc["name"],
                            arguments=tc["arguments"],
                            result_summary=tc.get("result_summary"),
                        )
                        for tc in response.tool_calls_made
                    ],
                    sources=[
                        SourceReference(**src)
                        for src in response.sources
                    ],
                    tokens_used=response.tokens_used,
                )
                event = StreamEvent(
                    type="complete",
                    response=message_response,
                )
                yield f"data: {event.model_dump_json()}\n\n"

    except Exception as e:
        logger.error(f"Error streaming response: {e}")
        event = StreamEvent(type="error", message=str(e))
        yield f"data: {event.model_dump_json()}\n\n"
