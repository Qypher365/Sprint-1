"use client"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Separator } from "@/components/ui/separator"
import { SignalBadge } from "./status-badge"
import { ConfidenceGauge } from "./confidence-gauge"
import type { Agent } from "@/lib/mock-data"

export function AgentDetailDialog({
  agent,
  open,
  onOpenChange,
}: {
  agent: Agent | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  if (!agent) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 pr-6">
            <DialogTitle>{agent.name}</DialogTitle>
            {agent.signal && <SignalBadge signal={agent.signal} />}
          </div>
          <DialogDescription>{agent.role}</DialogDescription>
        </DialogHeader>

        {agent.confidence !== null && agent.signal && (
          <div className="flex items-center justify-center py-2">
            <ConfidenceGauge confidence={agent.confidence} signal={agent.signal} />
          </div>
        )}

        {agent.metrics && (
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(agent.metrics).map(([key, value]) => (
              <div key={key} className="rounded-lg bg-muted p-2.5">
                <p className="text-[11px] text-muted-foreground">{key}</p>
                <p className="text-sm font-medium tabular-nums">{value}</p>
              </div>
            ))}
          </div>
        )}

        <Separator />

        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Reasoning timeline</p>
          <ol className="flex flex-col gap-3">
            {agent.timeline?.map((step, i) => (
              <li key={i} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="mt-1 size-1.5 shrink-0 rounded-full bg-primary" />
                  {i < (agent.timeline?.length ?? 0) - 1 && (
                    <span className="mt-1 w-px flex-1 bg-border" />
                  )}
                </div>
                <div className="pb-1">
                  <p className="text-xs text-muted-foreground">{step.label}</p>
                  <p className="text-sm font-medium">{step.value}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </DialogContent>
    </Dialog>
  )
}
