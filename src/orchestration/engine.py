"""LLM orchestration engine for Azure OpenAI integration.

This module provides the core engine for interacting with Azure OpenAI,
handling streaming responses, and managing function/tool calling.
"""

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncAzureOpenAI, APIError, RateLimitError

from .models import Message, MessageRole, StreamChunk, ToolCall, UsageInfo

logger = logging.getLogger(__name__)


class OrchestrationEngine:
    """Main orchestration engine for LLM interactions.

    Handles:
    - Message formatting for Azure OpenAI API
    - Function calling with tool definitions
    - Response streaming
    - Retry logic with backoff
    - Token counting

    Example:
        engine = OrchestrationEngine(
            azure_endpoint="https://my-openai.openai.azure.com",
            model="gpt-4o",
        )

        messages = [Message(role=MessageRole.USER, content="Hello!")]
        async for chunk in engine.chat(messages):
            if chunk.content:
                print(chunk.content, end="")
    """

    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MODEL = "gpt-4o"
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0

    def __init__(
        self,
        azure_endpoint: str,
        model: str | None = None,
        api_key: str | None = None,
        api_version: str = "2024-06-01",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        """Initialize the orchestration engine.

        Args:
            azure_endpoint: Azure OpenAI endpoint URL
            model: Model deployment name (default: gpt-4o)
            api_key: API key (if None, uses DefaultAzureCredential)
            api_version: Azure OpenAI API version
            max_tokens: Maximum tokens in response
            temperature: Response temperature (0.0-1.0)
        """
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.api_version = api_version

        if api_key:
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version,
            )
        else:
            # Use Managed Identity / DefaultAzureCredential
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            self.client = AsyncAzureOpenAI(
                azure_endpoint=azure_endpoint,
                azure_ad_token_provider=token_provider,
                api_version=api_version,
            )

        self._last_usage: UsageInfo | None = None

    @property
    def last_usage(self) -> UsageInfo | None:
        """Get token usage from the last API call."""
        return self._last_usage

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[StreamChunk]:
        """Send messages to LLM and stream response.

        Args:
            messages: Conversation history
            tools: Available tools for function calling
            stream: Whether to stream the response

        Yields:
            StreamChunk objects with content or tool calls

        Raises:
            APIError: If API call fails after retries
        """
        formatted_messages = self._format_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

        if tools:
            kwargs["tools"] = self._format_tools(tools)
            kwargs["tool_choice"] = "auto"

        if stream:
            async for chunk in self._stream_with_retry(**kwargs):
                yield chunk
        else:
            response = await self._call_with_retry(**kwargs)
            for chunk in self._process_non_streaming_response(response):
                yield chunk

    async def _call_with_retry(self, **kwargs: Any) -> Any:
        """Make API call with retry logic."""
        import asyncio

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.client.chat.completions.create(**kwargs)

                # Track usage
                if hasattr(response, "usage") and response.usage:
                    self._last_usage = UsageInfo(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                    )

                return response

            except RateLimitError as e:
                last_error = e
                delay = self.RETRY_DELAY_BASE * (2**attempt)
                logger.warning(
                    f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(delay)

            except APIError as e:
                last_error = e
                if e.status_code and e.status_code >= 500:
                    delay = self.RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        f"Server error {e.status_code}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise last_error or APIError("Max retries exceeded")

    async def _stream_with_retry(self, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        """Stream response with retry logic."""
        import asyncio

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async for chunk in self._stream_response(**kwargs):
                    yield chunk
                return

            except RateLimitError as e:
                last_error = e
                delay = self.RETRY_DELAY_BASE * (2**attempt)
                logger.warning(
                    f"Rate limited during stream, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(delay)

            except APIError as e:
                last_error = e
                if e.status_code and e.status_code >= 500:
                    delay = self.RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        f"Server error during stream, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise last_error or APIError("Max retries exceeded")

    async def _stream_response(self, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        """Stream response from OpenAI API."""
        tool_calls: dict[int, dict[str, Any]] = {}

        response = await self.client.chat.completions.create(**kwargs)

        async for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Handle content
            if delta.content:
                yield StreamChunk(content=delta.content)

            # Handle tool calls (accumulated across chunks)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }

                    if tc_delta.id:
                        tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tc_delta.function.arguments

            # Check finish reason
            finish_reason = chunk.choices[0].finish_reason
            if finish_reason:
                # Emit any accumulated tool calls
                for tc in tool_calls.values():
                    try:
                        arguments = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        arguments = {}
                        logger.warning(f"Failed to parse tool arguments: {tc['arguments']}")

                    yield StreamChunk(
                        tool_call=ToolCall(
                            id=tc["id"],
                            name=tc["name"],
                            arguments=arguments,
                        )
                    )

                yield StreamChunk(finish_reason=finish_reason)

    def _process_non_streaming_response(self, response: Any) -> list[StreamChunk]:
        """Process non-streaming response into chunks."""
        chunks: list[StreamChunk] = []
        choice = response.choices[0]

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                    logger.warning(f"Failed to parse tool arguments: {tc.function.arguments}")

                chunks.append(
                    StreamChunk(
                        tool_call=ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=arguments,
                        )
                    )
                )

        if choice.message.content:
            chunks.append(StreamChunk(content=choice.message.content))

        chunks.append(StreamChunk(finish_reason=choice.finish_reason))
        return chunks

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Format messages for OpenAI API."""
        formatted = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            formatted.append(m)
        return formatted

    def _format_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format tools for OpenAI API function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]

    async def count_tokens(self, messages: list[Message]) -> int:
        """Estimate token count for messages.

        This uses tiktoken for accurate token counting.

        Args:
            messages: Messages to count tokens for

        Returns:
            Estimated token count
        """
        try:
            import tiktoken
        except ImportError:
            # Rough estimate if tiktoken not available
            text = " ".join(m.content for m in messages)
            return len(text) // 4

        try:
            # Use cl100k_base encoding (GPT-4 family)
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback to rough estimate
            text = " ".join(m.content for m in messages)
            return len(text) // 4

        total = 0
        for msg in messages:
            # Each message has overhead
            total += 4  # <|start|>role<|end|>
            total += len(encoding.encode(msg.content))
            if msg.name:
                total += len(encoding.encode(msg.name))

        return total

    async def close(self) -> None:
        """Close the client connection."""
        await self.client.close()
