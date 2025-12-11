import { Routes, Route, Navigate, useSearchParams } from "react-router-dom"
import { AuthenticatedTemplate, UnauthenticatedTemplate } from "@azure/msal-react"
import { ChatPage } from "@/components/Chat/ChatPage"
import { LoginPage } from "@/components/LoginPage"

// Test mode component that bypasses auth for visual testing
function TestModeWrapper({ children }: { children: React.ReactNode }) {
  const [searchParams] = useSearchParams()
  const isTestMode = searchParams.get("test") === "true"

  if (isTestMode) {
    return <>{children}</>
  }

  return (
    <>
      <AuthenticatedTemplate>{children}</AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <Routes>
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </UnauthenticatedTemplate>
    </>
  )
}

function App() {
  return (
    <div className="min-h-screen bg-background">
      <TestModeWrapper>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat/:conversationId?" element={<ChatPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </TestModeWrapper>
    </div>
  )
}

export default App
