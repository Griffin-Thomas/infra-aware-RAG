import { useState, useCallback, useRef } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createConversation,
  sendMessage,
  listConversations,
  getConversation,
  deleteConversation,
} from "@/services/api"
import type { Message, ToolCall, Source } from "@/types"

interface ChatCallbacks {
  onToken: (token: string) => void
  onToolCall: (toolCall: ToolCall) => void
  onComplete: (response: {
    content: string
    toolCallsMade: ToolCall[]
    sources: Source[]
  }) => void
  onError: (error: Error) => void
}

export function useChat() {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentToolCalls, setCurrentToolCalls] = useState<ToolCall[]>([])
  const abortControllerRef = useRef<AbortController | null>(null)
  const queryClient = useQueryClient()

  // Create a new conversation
  const createConversationMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (data) => {
      setConversationId(data.id)
      setMessages([])
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const startNewConversation = useCallback(async () => {
    const result = await createConversationMutation.mutateAsync()
    return result.id
  }, [createConversationMutation])

  // Send a message
  const sendMessageAsync = useCallback(
    async (content: string, callbacks: ChatCallbacks) => {
      if (!conversationId) {
        throw new Error("No conversation")
      }

      // Cancel any existing request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      abortControllerRef.current = new AbortController()

      setIsLoading(true)
      setCurrentToolCalls([])

      // Add user message
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, userMessage])

      // Add placeholder for assistant
      const assistantMessageId = crypto.randomUUID()
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isStreaming: true,
      }
      setMessages((prev) => [...prev, assistantMessage])

      try {
        await sendMessage(
          conversationId,
          content,
          {
            onToken: (token: string) => {
              setMessages((prev) => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last.role === "assistant") {
                  last.content += token
                }
                return updated
              })
              callbacks.onToken(token)
            },
            onToolCall: (toolCall: ToolCall) => {
              setCurrentToolCalls((prev) => [...prev, toolCall])
              callbacks.onToolCall(toolCall)
            },
            onComplete: (response) => {
              setMessages((prev) => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last.role === "assistant") {
                  last.isStreaming = false
                  last.toolCalls = response.toolCallsMade
                  last.sources = response.sources
                }
                return updated
              })
              setCurrentToolCalls([])
              callbacks.onComplete(response)
            },
            onError: (error: Error) => {
              setMessages((prev) => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last.role === "assistant") {
                  last.content = `Error: ${error.message}`
                  last.isStreaming = false
                }
                return updated
              })
              callbacks.onError(error)
            },
          },
          abortControllerRef.current.signal
        )
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return // Request was cancelled
        }
        callbacks.onError(
          error instanceof Error ? error : new Error("Unknown error")
        )
      } finally {
        setIsLoading(false)
      }
    },
    [conversationId]
  )

  // Cancel current request
  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setIsLoading(false)
  }, [])

  // Load an existing conversation
  const loadConversation = useCallback(async (id: string) => {
    const data = await getConversation(id)
    setConversationId(data.id)
    setMessages(
      data.messages.map((m) => ({
        ...m,
        timestamp: new Date(m.timestamp),
      }))
    )
    return data
  }, [])

  return {
    conversationId,
    messages,
    isLoading,
    currentToolCalls,
    createConversation: startNewConversation,
    sendMessage: sendMessageAsync,
    cancelRequest,
    loadConversation,
    setConversationId,
    setMessages,
  }
}

// Hook for listing conversations
export function useConversations(enabled = true) {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
    staleTime: 30000, // 30 seconds
    enabled,
    retry: enabled ? 1 : false,
  })
}

// Hook for deleting a conversation
export function useDeleteConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })
}

// Hook for loading a specific conversation
export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ["conversation", id],
    queryFn: () => (id ? getConversation(id) : null),
    enabled: !!id,
  })
}
