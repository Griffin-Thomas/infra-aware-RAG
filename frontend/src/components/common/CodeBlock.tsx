import { useState } from "react"
import { cn } from "@/lib/utils"
import { Check, Copy } from "lucide-react"

interface CodeBlockProps {
  language: string
  value: string
}

export function CodeBlock({ language, value }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative my-4 overflow-hidden rounded-lg border bg-muted">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-2">
        <span className="text-xs font-medium text-muted-foreground">
          {language}
        </span>
        <button
          onClick={handleCopy}
          className={cn(
            "flex items-center gap-1.5 rounded px-2 py-1 text-xs",
            "text-muted-foreground hover:bg-background hover:text-foreground",
            "transition-colors"
          )}
        >
          {copied ? (
            <>
              <Check className="h-3 w-3" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Code */}
      <pre className="overflow-x-auto p-4">
        <code className="text-sm font-mono">{value}</code>
      </pre>
    </div>
  )
}
