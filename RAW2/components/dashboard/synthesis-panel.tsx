import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { SignalBadge } from "./status-badge"
import { ConfidenceGauge } from "./confidence-gauge"
import { AlertTriangleIcon, SparklesIcon, ClockIcon } from "lucide-react"
import type { Synthesis, RiskProfile, SessionMetrics } from "@/lib/mock-data"

export function SynthesisPanel({
  synthesis,
  riskProfile,
  metrics,
  agentsExcluded,
  empty,
}: {
  synthesis: Synthesis | null
  riskProfile: RiskProfile
  metrics: SessionMetrics
  agentsExcluded: number
  empty?: boolean
}) {
  if (empty || !synthesis) {
    return (
      <Card className="py-4">
        <CardContent className="px-4">
          <Empty className="p-0">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <ClockIcon />
              </EmptyMedia>
              <EmptyTitle>Not enough data yet</EmptyTitle>
              <EmptyDescription>
                Coverage for this asset is still being collected. Synthesis will appear once
                agents report sufficient confidence.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="gap-4 py-4">
      <CardHeader className="px-4">
        <div className="flex items-center gap-2">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
            <SparklesIcon className="size-3.5" aria-hidden="true" />
          </div>
          <CardTitle className="text-sm">Synthesized signal</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Weighted consensus across active agents
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-4">
        {synthesis.conflicting && (
          <Alert>
            <AlertTriangleIcon />
            <AlertTitle>Conflicting signals</AlertTitle>
            <AlertDescription>
              Agents disagree on direction. Synthesis confidence reflects this uncertainty.
            </AlertDescription>
          </Alert>
        )}

        {agentsExcluded > 0 && (
          <Alert>
            <AlertTriangleIcon />
            <AlertTitle>Partial coverage</AlertTitle>
            <AlertDescription>
              {agentsExcluded} agent{agentsExcluded > 1 ? "s" : ""} unavailable and excluded from
              this synthesis.
            </AlertDescription>
          </Alert>
        )}

        <div className="flex items-center gap-4">
          <ConfidenceGauge confidence={synthesis.confidence} signal={synthesis.signal} size={104} />
          <div className="flex flex-col gap-2">
            <SignalBadge signal={synthesis.signal} />
            <p className="text-sm leading-relaxed text-muted-foreground">{synthesis.summary}</p>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Key reasons</p>
          <ul className="flex flex-col gap-1.5">
            {synthesis.reasons.map((reason) => (
              <li key={reason} className="flex items-start gap-2 text-sm">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-foreground/60" />
                {reason}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg bg-surface p-3 ring-1 ring-border">
          <p className="text-xs font-medium text-muted-foreground">
            Impact for {riskProfile === "conservative" ? "conservative" : "aggressive"} profile
          </p>
          <p className="mt-1 text-sm leading-relaxed">{synthesis.riskImpact[riskProfile]}</p>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <MetricTile label="Latency" value={`${metrics.latencyMs}ms`} />
          <MetricTile label="Risk concentration" value={`${metrics.riskConcentrationPct}%`} />
          <MetricTile label="Accuracy" value={`${metrics.accuracyPct}%`} />
        </div>
      </CardContent>
    </Card>
  )
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted p-2.5 text-center">
      <p className="text-sm font-semibold tabular-nums">{value}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}
