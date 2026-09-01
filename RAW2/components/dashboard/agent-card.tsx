"use client"

import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"
import { SignalBadge } from "./status-badge"
import {
  LineChartIcon,
  NewspaperIcon,
  FileTextIcon,
  AlertTriangleIcon,
  InfoIcon,
} from "lucide-react"
import type { Agent } from "@/lib/mock-data"

const AGENT_ICON: Record<string, typeof LineChartIcon> = {
  technical: LineChartIcon,
  sentiment: NewspaperIcon,
  fundamental: FileTextIcon,
}

export function AgentCard({ agent, onOpen }: { agent: Agent; onOpen: () => void }) {
  const Icon = AGENT_ICON[agent.id] ?? LineChartIcon

  return (
    <Card
      role="button"
      tabIndex={agent.status === "complete" ? 0 : -1}
      onClick={() => agent.status === "complete" && onOpen()}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && agent.status === "complete") {
          e.preventDefault()
          onOpen()
        }
      }}
      className={
        agent.status === "complete"
          ? "cursor-pointer gap-3 py-4 transition-colors hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          : "gap-3 py-4"
      }
    >
      <CardHeader className="gap-2 px-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-foreground">
              <Icon className="size-3.5" aria-hidden="true" />
            </div>
            <CardTitle className="text-sm">{agent.name}</CardTitle>
          </div>
          {agent.status === "complete" && agent.signal && (
            <SignalBadge signal={agent.signal} />
          )}
        </div>
        <CardDescription className="text-xs">{agent.role}</CardDescription>
      </CardHeader>
      <CardContent className="px-4">
        {agent.status === "processing" && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-3.5 w-4/5" />
            <Skeleton className="h-3.5 w-3/5" />
          </div>
        )}

        {agent.status === "error" && (
          <Alert variant="destructive">
            <AlertTriangleIcon />
            <AlertTitle>Agent unavailable</AlertTitle>
            <AlertDescription>{agent.summary}</AlertDescription>
          </Alert>
        )}

        {agent.status === "idle" && (
          <Alert>
            <InfoIcon />
            <AlertTitle>Awaiting data</AlertTitle>
            <AlertDescription>{agent.summary}</AlertDescription>
          </Alert>
        )}

        {agent.status === "complete" && (
          <Tooltip>
            <TooltipTrigger
              render={
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {agent.summary}
                </p>
              }
            />
            <TooltipContent>{agent.hoverDetail}</TooltipContent>
          </Tooltip>
        )}

        {agent.status === "complete" && agent.confidence !== null && (
          <div className="mt-3 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${agent.confidence}%` }}
              />
            </div>
            <span className="text-xs font-medium tabular-nums text-muted-foreground">
              {agent.confidence}%
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
