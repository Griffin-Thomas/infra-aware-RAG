import { useEffect, useRef, useMemo } from "react"
import { useParams, useNavigate, useSearchParams } from "react-router-dom"
import { useChat, useConversations } from "@/hooks/useChat"
import { useAuth } from "@/hooks/useAuth"
import { ChatContainer } from "./ChatContainer"
import { ConversationSidebar } from "@/components/Sidebar/ConversationSidebar"
import { Header } from "@/components/common/Header"

export function ChatPage() {
  const { conversationId: urlConversationId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isTestMode = searchParams.get("test") === "true"
  const { user, logout } = useAuth()
  const {
    conversationId,
    messages,
    isLoading,
    currentToolCalls,
    createConversation,
    sendMessage,
    cancelRequest,
    loadConversation,
    setConversationId,
    setMessages,
  } = useChat()
  const { data: conversations, refetch: refetchConversations } = useConversations(!isTestMode)
  const initialLoadRef = useRef(false)

  // In test mode, set up mock data
  useEffect(() => {
    if (isTestMode && !conversationId) {
      setConversationId("test-conversation-id")
      setMessages([])
    }
  }, [isTestMode, conversationId, setConversationId, setMessages])

  // Mock conversations for test mode
  const displayConversations = useMemo(() => {
    if (isTestMode) {
      return []
    }
    return conversations || []
  }, [isTestMode, conversations])

  // Handle URL-based conversation loading
  useEffect(() => {
    if (initialLoadRef.current || isTestMode) return
    initialLoadRef.current = true

    const loadFromUrl = async () => {
      if (urlConversationId && urlConversationId !== conversationId) {
        try {
          await loadConversation(urlConversationId)
        } catch (error) {
          console.error("Failed to load conversation:", error)
          navigate("/", { replace: true })
        }
      } else if (!urlConversationId && !conversationId) {
        // Create new conversation on initial load
        try {
          const newId = await createConversation()
          navigate(`/chat/${newId}`, { replace: true })
        } catch (error) {
          console.error("Failed to create conversation:", error)
        }
      }
    }

    loadFromUrl()
  }, [urlConversationId, conversationId, loadConversation, createConversation, navigate, isTestMode])

  // Update URL when conversation changes (skip in test mode to preserve query params)
  useEffect(() => {
    if (isTestMode) return
    if (conversationId && conversationId !== urlConversationId) {
      navigate(`/chat/${conversationId}`, { replace: true })
    }
  }, [conversationId, urlConversationId, navigate, isTestMode])

  const handleNewConversation = async () => {
    const newId = await createConversation()
    navigate(`/chat/${newId}`)
  }

  const handleSelectConversation = async (id: string) => {
    if (id !== conversationId) {
      await loadConversation(id)
      navigate(`/chat/${id}`)
    }
  }

  const handleSendMessage = async (content: string) => {
    await sendMessage(content, {
      onToken: () => {},
      onToolCall: () => {},
      onComplete: () => {
        refetchConversations()
      },
      onError: (error) => {
        console.error("Message error:", error)
      },
    })
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <ConversationSidebar
        conversations={displayConversations}
        currentConversationId={conversationId}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
      />

      {/* Main content */}
      <div className="flex flex-1 flex-col">
        <Header user={user} onLogout={logout} />
        <ChatContainer
          messages={messages}
          isLoading={isLoading}
          currentToolCalls={currentToolCalls}
          onSendMessage={handleSendMessage}
          onCancel={cancelRequest}
        />
      </div>
    </div>
  )
}
