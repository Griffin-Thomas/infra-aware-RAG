import { useState, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from "react"
import { cn } from "@/lib/utils"
import { Send, Square } from "lucide-react"

interface InputBarProps {
  onSend: (content: string) => void
  onCancel?: () => void
  disabled?: boolean
  isLoading?: boolean
  placeholder?: string
}

export function InputBar({
  onSend,
  onCancel,
  disabled = false,
  isLoading = false,
  placeholder = "Type a message...",
}: InputBarProps) {
  const [input, setInput] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = "auto"
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [input])

  const handleSubmit = () => {
    if (input.trim() && !disabled) {
      onSend(input.trim())
      setInput("")
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
  }

  return (
    <div className="border-t bg-background p-4">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-end gap-2 rounded-lg border bg-card p-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className={cn(
              "flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none",
              "placeholder:text-muted-foreground",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          />

          {isLoading ? (
            <button
              onClick={onCancel}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-md",
                "bg-destructive text-destructive-foreground",
                "hover:bg-destructive/90 transition-colors"
              )}
              title="Stop generating"
            >
              <Square className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || disabled}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-md",
                "bg-primary text-primary-foreground",
                "hover:bg-primary/90 transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
              title="Send message"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>

        <p className="mt-2 text-center text-xs text-muted-foreground">
          Press Enter to send, Shift+Enter for a new line
        </p>
      </div>
    </div>
  )
}
