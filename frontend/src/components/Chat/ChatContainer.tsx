import { useRef, useEffect } from "react"
import { MessageList } from "./MessageList"
import { InputBar } from "./InputBar"
import { ToolCallDisplay } from "./ToolCallDisplay"
import type { Message, ToolCall } from "@/types"

interface ChatContainerProps {
  messages: Message[]
  isLoading: boolean
  currentToolCalls: ToolCall[]
  onSendMessage: (content: string) => Promise<void>
  onCancel: () => void
}

export function ChatContainer({
  messages,
  isLoading,
  currentToolCalls,
  onSendMessage,
  onCancel,
}: ChatContainerProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, currentToolCalls])

  const handleSend = async (content: string) => {
    if (!content.trim() || isLoading) return
    await onSendMessage(content)
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <MessageList messages={messages} />

            {/* Tool calls in progress */}
            {currentToolCalls.length > 0 && (
              <ToolCallDisplay toolCalls={currentToolCalls} />
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <InputBar
        onSend={handleSend}
        onCancel={onCancel}
        disabled={isLoading}
        isLoading={isLoading}
        placeholder="Ask about your infrastructure..."
      />
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <div className="max-w-md space-y-4">
        <h2 className="text-2xl font-semibold text-foreground">
          Welcome to Infra-Aware Assistant
        </h2>
        <p className="text-muted-foreground">
          Ask questions about your Azure infrastructure and Terraform code.
          I can help you:
        </p>
        <ul className="space-y-2 text-left text-sm text-muted-foreground">
          <li className="flex items-start gap-2">
            <span className="mt-1 text-primary">*</span>
            <span>Search and explore Azure resources across subscriptions</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 text-primary">*</span>
            <span>Find Terraform code that manages specific resources</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 text-primary">*</span>
            <span>Analyze Terraform plans and explain changes</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 text-primary">*</span>
            <span>Track Git history for infrastructure changes</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 text-primary">*</span>
            <span>Understand resource dependencies and relationships</span>
          </li>
        </ul>
        <div className="pt-4">
          <p className="text-xs text-muted-foreground">
            Try asking: "What VMs do we have in production?" or "Show me the Terraform for our main database"
          </p>
        </div>
      </div>
    </div>
  )
}
