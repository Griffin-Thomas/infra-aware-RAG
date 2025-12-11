// Chat types
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCall[]
  sources?: Source[]
  timestamp: Date
  isStreaming?: boolean
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  resultSummary?: string
}

export interface Source {
  type: 'azure_resource' | 'terraform' | 'git_commit'
  id?: string
  address?: string
  sha?: string
}

// Conversation types
export interface Conversation {
  id: string
  title?: string
  created_at: string
  updated_at: string
  message_count?: number
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

// API types
export interface SearchRequest {
  query: string
  top?: number
  doc_types?: string[]
  filters?: Record<string, unknown>
  include_facets?: boolean
}

export interface SearchResult {
  id: string
  doc_type: string
  content: string
  score: number
  highlights?: string[]
  metadata?: Record<string, unknown>
}

export interface SearchResponse {
  results: SearchResult[]
  total_count: number
  facets?: Record<string, Array<{ value: string; count: number }>>
}

// SSE Event types
export interface SSETokenEvent {
  type: 'token'
  content: string
}

export interface SSEToolCallEvent {
  type: 'tool_call'
  toolCall: ToolCall
}

export interface SSECompleteEvent {
  type: 'complete'
  response: {
    content: string
    toolCallsMade: ToolCall[]
    sources: Source[]
  }
}

export interface SSEErrorEvent {
  type: 'error'
  message: string
}

export type SSEEvent = SSETokenEvent | SSEToolCallEvent | SSECompleteEvent | SSEErrorEvent

// User types
export interface User {
  id: string
  name: string
  email: string
}
