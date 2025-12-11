import { cn } from "@/lib/utils"
import { Cloud, FileCode, GitCommit } from "lucide-react"
import type { Source } from "@/types"

interface ResourceLinkProps {
  source: Source
}

export function ResourceLink({ source }: ResourceLinkProps) {
  const getIcon = () => {
    switch (source.type) {
      case "azure_resource":
        return <Cloud className="h-3 w-3" />
      case "terraform":
        return <FileCode className="h-3 w-3" />
      case "git_commit":
        return <GitCommit className="h-3 w-3" />
      default:
        return null
    }
  }

  const getLabel = () => {
    switch (source.type) {
      case "azure_resource":
        return source.id?.split("/").pop() || "Resource"
      case "terraform":
        return source.address || "Terraform"
      case "git_commit":
        return source.sha?.slice(0, 7) || "Commit"
      default:
        return "Unknown"
    }
  }

  const getColorClass = () => {
    switch (source.type) {
      case "azure_resource":
        return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30"
      case "terraform":
        return "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30"
      case "git_commit":
        return "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30"
      default:
        return "bg-muted text-muted-foreground"
    }
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium",
        getColorClass()
      )}
      title={
        source.type === "azure_resource"
          ? source.id
          : source.type === "terraform"
          ? source.address
          : source.sha
      }
    >
      {getIcon()}
      <span className="max-w-32 truncate">{getLabel()}</span>
    </span>
  )
}
