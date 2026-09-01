import { ActivityIcon } from "lucide-react"
import { LiveDot } from "./status-badge"

export function DashboardHeader({ degraded }: { degraded: boolean }) {
  return (
    <header className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <div className="flex items-center gap-2.5">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <ActivityIcon className="size-4" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-sm font-semibold leading-none text-foreground">
            AI Financial Intelligence
          </h1>
          <p className="mt-1 text-xs leading-none text-muted-foreground">
            Multi-agent signal synthesis
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {degraded ? (
          <>
            <span className="relative flex size-1.5 rounded-full bg-destructive" />
            Connection degraded
          </>
        ) : (
          <>
            <LiveDot />
            Live session
          </>
        )}
      </div>
    </header>
  )
}
