import { Loader2 } from "lucide-react"
import type { ToolCall } from "@/types"

interface ToolCallDisplayProps {
  toolCalls: ToolCall[]
}

export function ToolCallDisplay({ toolCalls }: ToolCallDisplayProps) {
  if (toolCalls.length === 0) return null

  return (
    <div className="my-4 rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-yellow-600 dark:text-yellow-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Using tools...</span>
      </div>
      <div className="mt-2 space-y-2">
        {toolCalls.map((toolCall, index) => (
          <div
            key={index}
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <span className="font-mono text-xs">{toolCall.name}</span>
            {toolCall.resultSummary && (
              <span className="text-xs">- {toolCall.resultSummary}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
