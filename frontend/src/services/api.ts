import { getAccessToken } from "./auth"
import type {
  Conversation,
  ConversationDetail,
  SearchRequest,
  SearchResponse,
  ToolCall,
  Source,
} from "@/types"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1"

// Helper to get auth headers
async function getAuthHeaders(): Promise<HeadersInit> {
  const token = await getAccessToken()
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  return headers
}

// Generic API request helper
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      ...headers,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// ============== Conversation API ==============

export async function createConversation(): Promise<Conversation> {
  return apiRequest<Conversation>("/conversations", {
    method: "POST",
  })
}

export async function listConversations(): Promise<Conversation[]> {
  return apiRequest<Conversation[]>("/conversations")
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/conversations/${id}`)
}

export async function deleteConversation(id: string): Promise<void> {
  await apiRequest<void>(`/conversations/${id}`, {
    method: "DELETE",
  })
}

// SSE response types
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

// Send message with SSE streaming
export async function sendMessage(
  conversationId: string,
  content: string,
  callbacks: {
    onToken: (token: string) => void
    onToolCall: (toolCall: ToolCall) => void
    onComplete: (response: { content: string; toolCallsMade: ToolCall[]; sources: Source[] }) => void
    onError: (error: Error) => void
  },
  signal?: AbortSignal
): Promise<void> {
  const headers = await getAuthHeaders()

  const response = await fetch(
    `${API_BASE_URL}/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ content }),
      signal,
    }
  )

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  // Handle SSE streaming response
  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) {
    throw new Error("No response body")
  }

  let buffer = ""

  try {
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
                callbacks.onToken(data.content)
                break
              case "tool_call":
                callbacks.onToolCall(data.toolCall)
                break
              case "complete":
                callbacks.onComplete(data.response)
                break
              case "error":
                callbacks.onError(new Error(data.message))
                break
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

// ============== Search API ==============

export async function search(request: SearchRequest): Promise<SearchResponse> {
  return apiRequest<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify(request),
  })
}

export async function searchWithGraphExpansion(
  request: SearchRequest
): Promise<SearchResponse> {
  return apiRequest<SearchResponse>("/search/expand", {
    method: "POST",
    body: JSON.stringify(request),
  })
}

// ============== Resources API ==============

export interface AzureResource {
  id: string
  name: string
  type: string
  location: string
  resource_group: string
  subscription_id: string
  properties: Record<string, unknown>
  tags?: Record<string, string>
}

export async function getResource(resourceId: string): Promise<AzureResource> {
  return apiRequest<AzureResource>(`/resources/${encodeURIComponent(resourceId)}`)
}

export async function getResourceTerraform(
  resourceId: string
): Promise<{ terraform_resources: unknown[] }> {
  return apiRequest<{ terraform_resources: unknown[] }>(
    `/resources/${encodeURIComponent(resourceId)}/terraform`
  )
}

export async function getResourceDependencies(
  resourceId: string
): Promise<{ dependencies: unknown[] }> {
  return apiRequest<{ dependencies: unknown[] }>(
    `/resources/${encodeURIComponent(resourceId)}/dependencies`
  )
}

export async function queryResourceGraph(
  query: string
): Promise<{ results: unknown[] }> {
  return apiRequest<{ results: unknown[] }>("/resource-graph/query", {
    method: "POST",
    body: JSON.stringify({ query }),
  })
}

// ============== Terraform API ==============

export interface TerraformResource {
  address: string
  type: string
  name: string
  provider: string
  source_file?: string
  line_number?: number
}

export async function listTerraformResources(): Promise<{
  resources: TerraformResource[]
}> {
  return apiRequest<{ resources: TerraformResource[] }>("/terraform/resources")
}

export async function getTerraformResource(
  address: string
): Promise<TerraformResource> {
  return apiRequest<TerraformResource>(
    `/terraform/resources/${encodeURIComponent(address)}`
  )
}

export interface TerraformPlan {
  id: string
  timestamp: string
  changes_summary: {
    create: number
    update: number
    delete: number
    replace: number
  }
}

export async function listTerraformPlans(): Promise<{ plans: TerraformPlan[] }> {
  return apiRequest<{ plans: TerraformPlan[] }>("/terraform/plans")
}

export async function getTerraformPlan(planId: string): Promise<TerraformPlan> {
  return apiRequest<TerraformPlan>(`/terraform/plans/${planId}`)
}

export async function analyzeTerraformPlan(
  planId: string
): Promise<{ analysis: string }> {
  return apiRequest<{ analysis: string }>(`/terraform/plans/${planId}/analyze`, {
    method: "POST",
  })
}

// ============== Git API ==============

export interface GitCommit {
  sha: string
  message: string
  author: string
  author_email: string
  timestamp: string
  terraform_changes: boolean
}

export async function listGitCommits(params?: {
  limit?: number
  terraform_only?: boolean
  author?: string
  since?: string
  until?: string
}): Promise<{ commits: GitCommit[] }> {
  const searchParams = new URLSearchParams()
  if (params?.limit) searchParams.set("limit", String(params.limit))
  if (params?.terraform_only) searchParams.set("terraform_only", "true")
  if (params?.author) searchParams.set("author", params.author)
  if (params?.since) searchParams.set("since", params.since)
  if (params?.until) searchParams.set("until", params.until)

  const query = searchParams.toString()
  return apiRequest<{ commits: GitCommit[] }>(
    `/git/commits${query ? `?${query}` : ""}`
  )
}

export async function getGitCommit(sha: string): Promise<GitCommit> {
  return apiRequest<GitCommit>(`/git/commits/${sha}`)
}

export async function getGitCommitDiff(
  sha: string
): Promise<{ diff: string; files_changed: string[] }> {
  return apiRequest<{ diff: string; files_changed: string[] }>(
    `/git/commits/${sha}/diff`
  )
}

// ============== Tools API ==============

export interface ToolDefinition {
  name: string
  description: string
  parameters: Record<string, unknown>
}

export async function listTools(): Promise<{ tools: ToolDefinition[] }> {
  return apiRequest<{ tools: ToolDefinition[] }>("/tools")
}

export async function executeTool(
  name: string,
  parameters: Record<string, unknown>
): Promise<{ result: unknown }> {
  return apiRequest<{ result: unknown }>("/tools/execute", {
    method: "POST",
    body: JSON.stringify({ name, parameters }),
  })
}
