import { useCallback, useRef, useState } from "react"
import type { ToolCall, Source } from "@/types"

// Local SSE types for this hook
interface SSETokenEvent {
  type: "token"
  content: string
}

interface SSEToolCallEvent {
  type: "tool_call"
  toolCall: ToolCall
}

interface SSECompleteEvent {
  type: "complete"
  response: {
    content: string
    toolCallsMade: ToolCall[]
    sources: Source[]
  }
}

interface SSEErrorEvent {
  type: "error"
  message: string
}

type SSEEvent = SSETokenEvent | SSEToolCallEvent | SSECompleteEvent | SSEErrorEvent

interface UseStreamOptions {
  onToken?: (token: string) => void
  onToolCall?: (toolCall: ToolCall) => void
  onComplete?: (response: { content: string; toolCallsMade: ToolCall[]; sources: Source[] }) => void
  onError?: (error: Error) => void
}

export function useStream(options: UseStreamOptions = {}) {
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const startStream = useCallback(
    async (url: string, body: unknown, headers: HeadersInit = {}) => {
      // Cancel any existing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      abortControllerRef.current = new AbortController()

      setIsStreaming(true)
      setError(null)

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...headers,
          },
          body: JSON.stringify(body),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: "Request failed" }))
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const reader = response.body?.getReader()
        const decoder = new TextDecoder()

        if (!reader) {
          throw new Error("No response body")
        }

        let buffer = ""

        while (true) {
          const { done, value } = await reader.read()

          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Process SSE events
          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6)) as SSEEvent

                switch (data.type) {
                  case "token":
                    options.onToken?.(data.content)
                    break
                  case "tool_call":
                    options.onToolCall?.(data.toolCall)
                    break
                  case "complete":
                    options.onComplete?.(data.response)
                    break
                  case "error": {
                    const err = new Error(data.message)
                    setError(err)
                    options.onError?.(err)
                    break
                  }
                }
              } catch {
                // Skip malformed JSON
              }
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          return // Request was cancelled
        }
        const error = err instanceof Error ? err : new Error("Unknown error")
        setError(error)
        options.onError?.(error)
      } finally {
        setIsStreaming(false)
      }
    },
    [options]
  )

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setIsStreaming(false)
  }, [])

  return {
    isStreaming,
    error,
    startStream,
    cancelStream,
  }
}
