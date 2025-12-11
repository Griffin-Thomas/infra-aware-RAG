import { cn } from "@/lib/utils"
import { LogOut, User } from "lucide-react"
import type { User as UserType } from "@/types"

interface HeaderProps {
  user: UserType | null
  onLogout: () => void
}

export function Header({ user, onLogout }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-3">
      <div>
        <h1 className="text-lg font-semibold text-foreground">
          Infra-Aware Assistant
        </h1>
        <p className="text-xs text-muted-foreground">
          Azure infrastructure and Terraform insights
        </p>
      </div>

      {user && (
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
              <User className="h-4 w-4" />
            </div>
            <div className="hidden sm:block">
              <p className="font-medium">{user.name}</p>
              <p className="text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>

          <button
            onClick={onLogout}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm",
              "text-muted-foreground hover:bg-muted hover:text-foreground",
              "transition-colors"
            )}
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      )}
    </header>
  )
}
