import { cn } from "@/lib/utils"
import { MessageSquarePlus, MessageSquare, Trash2 } from "lucide-react"
import { useDeleteConversation } from "@/hooks/useChat"
import type { Conversation } from "@/types"

interface ConversationSidebarProps {
  conversations: Conversation[]
  currentConversationId: string | null
  onNewConversation: () => void
  onSelectConversation: (id: string) => void
}

export function ConversationSidebar({
  conversations,
  currentConversationId,
  onNewConversation,
  onSelectConversation,
}: ConversationSidebarProps) {
  const deleteConversation = useDeleteConversation()

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (confirm("Delete this conversation?")) {
      await deleteConversation.mutateAsync(id)
      if (currentConversationId === id) {
        onNewConversation()
      }
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))

    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    } else if (diffDays === 1) {
      return "Yesterday"
    } else if (diffDays < 7) {
      return date.toLocaleDateString([], { weekday: "short" })
    } else {
      return date.toLocaleDateString([], { month: "short", day: "numeric" })
    }
  }

  return (
    <aside className="flex w-64 flex-col border-r bg-muted/30">
      {/* Header */}
      <div className="flex items-center justify-between border-b p-4">
        <h2 className="text-sm font-semibold">Conversations</h2>
        <button
          onClick={onNewConversation}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs",
            "bg-primary text-primary-foreground",
            "hover:bg-primary/90 transition-colors"
          )}
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          <span>New</span>
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto p-2">
        {conversations.length === 0 ? (
          <div className="px-2 py-8 text-center text-sm text-muted-foreground">
            No conversations yet
          </div>
        ) : (
          <div className="space-y-1">
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                onClick={() => onSelectConversation(conversation.id)}
                className={cn(
                  "group flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm",
                  "hover:bg-muted transition-colors",
                  conversation.id === currentConversationId && "bg-muted"
                )}
              >
                <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {conversation.title || "New conversation"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(conversation.updated_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(e, conversation.id)}
                  className={cn(
                    "hidden shrink-0 rounded p-1 text-muted-foreground",
                    "hover:bg-destructive/10 hover:text-destructive",
                    "group-hover:block transition-colors"
                  )}
                  title="Delete conversation"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t p-4">
        <p className="text-center text-xs text-muted-foreground">
          {conversations.length} conversation{conversations.length !== 1 ? "s" : ""}
        </p>
      </div>
    </aside>
  )
}
