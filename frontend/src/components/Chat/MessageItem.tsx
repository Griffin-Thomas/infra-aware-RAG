import ReactMarkdown from "react-markdown"
import { cn } from "@/lib/utils"
import { CodeBlock } from "@/components/common/CodeBlock"
import { ResourceLink } from "@/components/common/ResourceLink"
import type { Message } from "@/types"

interface MessageItemProps {
  message: Message
}

export function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === "user"

  return (
    <div
      className={cn(
        "flex gap-4 rounded-lg p-4",
        isUser ? "bg-muted/50" : "bg-card border"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white",
          isUser ? "bg-primary" : "bg-purple-600"
        )}
      >
        {isUser ? "U" : "A"}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            components={{
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "")
                const isInline = !match && !className

                if (isInline) {
                  return (
                    <code
                      className="rounded bg-muted px-1.5 py-0.5 text-sm font-mono"
                      {...props}
                    >
                      {children}
                    </code>
                  )
                }

                return (
                  <CodeBlock
                    language={match?.[1] || "text"}
                    value={String(children).replace(/\n$/, "")}
                  />
                )
              },
              pre({ children }) {
                return <>{children}</>
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>

        {/* Streaming indicator */}
        {message.isStreaming && (
          <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-purple-500" />
        )}

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-4 border-t pt-4">
            <h4 className="mb-2 text-sm font-medium text-muted-foreground">
              Sources
            </h4>
            <div className="flex flex-wrap gap-2">
              {message.sources.map((source, index) => (
                <ResourceLink key={index} source={source} />
              ))}
            </div>
          </div>
        )}

        {/* Tool calls made */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-4 border-t pt-4">
            <h4 className="mb-2 text-sm font-medium text-muted-foreground">
              Tools Used
            </h4>
            <div className="flex flex-wrap gap-2">
              {message.toolCalls.map((toolCall, index) => (
                <span
                  key={index}
                  className="inline-flex items-center rounded-md bg-muted px-2 py-1 text-xs font-medium"
                >
                  {toolCall.name}
                  {toolCall.resultSummary && (
                    <span className="ml-1 text-muted-foreground">
                      - {toolCall.resultSummary}
                    </span>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
