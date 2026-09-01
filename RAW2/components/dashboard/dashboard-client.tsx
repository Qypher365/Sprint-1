"use client"

import { useState } from "react"
import { DashboardHeader } from "./dashboard-header"
import { ControlsPanel } from "./controls-panel"
import { AgentCard } from "./agent-card"
import { AgentDetailDialog } from "./agent-detail-dialog"
import { SynthesisPanel } from "./synthesis-panel"
import { CitationsPanel } from "./citations-panel"
import { getStockData, type AssetSymbol, type RiskProfile, type Agent } from "@/lib/mock-data"
import { WifiOffIcon } from "lucide-react"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"

export function DashboardClient() {
  const [symbol, setSymbol] = useState<AssetSymbol>("RELIANCE")
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("conservative")
  const [networkFailure, setNetworkFailure] = useState(false)
  const [openAgent, setOpenAgent] = useState<Agent | null>(null)

  const asset = getStockData(symbol)
  const agentsExcluded = asset.agents.filter((a) => a.status === "error").length

  return (
    <div className="flex min-h-svh flex-col">
      <DashboardHeader degraded={networkFailure} />

      {networkFailure && (
        <div className="px-4 pt-4 sm:px-6">
          <Alert variant="destructive">
            <WifiOffIcon />
            <AlertTitle>Network connection degraded</AlertTitle>
            <AlertDescription>
              Live updates are paused. Showing the most recently cached data for {asset.symbol}.
            </AlertDescription>
          </Alert>
        </div>
      )}

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6 lg:flex-row lg:items-start">
        <aside className="w-full shrink-0 lg:w-64">
          <ControlsPanel
            asset={asset}
            symbol={symbol}
            onSymbolChange={setSymbol}
            riskProfile={riskProfile}
            onRiskProfileChange={setRiskProfile}
            networkFailure={networkFailure}
            onNetworkFailureChange={setNetworkFailure}
          />
        </aside>

        <div className="flex flex-1 flex-col gap-6">
          <section aria-label="Agent signals">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-sm font-semibold">Agent signals</h2>
              <span className="text-xs text-muted-foreground">
                {asset.symbol} · {asset.name}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {asset.agents.map((agent) => (
                <AgentCard key={agent.id} agent={agent} onOpen={() => setOpenAgent(agent)} />
              ))}
            </div>
          </section>

          <section aria-label="Synthesized signal">
            <SynthesisPanel
              synthesis={asset.synthesis}
              riskProfile={riskProfile}
              metrics={asset.metrics}
              agentsExcluded={agentsExcluded}
              empty={asset.empty}
            />
          </section>

          <section aria-label="Citations">
            <CitationsPanel citations={asset.citations} />
          </section>
        </div>
      </main>

      <AgentDetailDialog
        agent={openAgent}
        open={openAgent !== null}
        onOpenChange={(open) => !open && setOpenAgent(null)}
      />
    </div>
  )
}
