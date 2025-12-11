import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { MsalProvider } from "@azure/msal-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { BrowserRouter } from "react-router-dom"
import { msalInstance, initializeMsal } from "@/services/auth"
import App from "./App"
import "./index.css"

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute
      retry: 1,
    },
  },
})

// Initialize MSAL and render app
async function main() {
  try {
    await initializeMsal()
  } catch (error) {
    console.error("MSAL initialization failed:", error)
  }

  const root = createRoot(document.getElementById("root")!)

  root.render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
          <ReactQueryDevtools initialIsOpen={false} />
        </QueryClientProvider>
      </MsalProvider>
    </StrictMode>
  )
}

main()
