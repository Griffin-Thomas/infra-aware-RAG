import { useAuth } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"

export function LoginPage() {
  const { login } = useAuth()

  const handleLogin = async () => {
    try {
      await login()
    } catch (error) {
      console.error("Login error:", error)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="w-full max-w-md space-y-8 px-4">
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Infra-Aware Assistant
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            AI-powered insights for your Azure infrastructure and Terraform code
          </p>
        </div>

        <div className="rounded-lg border bg-card p-8 shadow-sm">
          <div className="space-y-6">
            <div className="space-y-2 text-center">
              <h2 className="text-xl font-semibold">Welcome</h2>
              <p className="text-sm text-muted-foreground">
                Sign in with your Entra ID account to get started
              </p>
            </div>

            <button
              onClick={handleLogin}
              className={cn(
                "w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground",
                "hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
                "transition-colors"
              )}
            >
              Sign in with Microsoft
            </button>

            <div className="text-center text-xs text-muted-foreground">
              <p>By signing in, you agree to use this tool responsibly.</p>
              <p className="mt-1">
                This assistant provides read-only access to your infrastructure data.
              </p>
            </div>
          </div>
        </div>

        <div className="text-center text-xs text-muted-foreground">
          <p>
            Questions about your infrastructure? Ask the assistant about:
          </p>
          <ul className="mt-2 space-y-1">
            <li>Azure resources and their configurations</li>
            <li>Terraform code and state files</li>
            <li>Git history for infrastructure changes</li>
            <li>Resource dependencies and relationships</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
