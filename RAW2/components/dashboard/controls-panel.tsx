"use client"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { ASSETS, type AssetSymbol, type RiskProfile } from "@/lib/mock-data"
import { SparklineChart } from "./sparkline-chart"
import type { StockData } from "@/lib/mock-data"

export function ControlsPanel({
  asset,
  symbol,
  onSymbolChange,
  riskProfile,
  onRiskProfileChange,
  networkFailure,
  onNetworkFailureChange,
}: {
  asset: StockData
  symbol: AssetSymbol
  onSymbolChange: (symbol: AssetSymbol) => void
  riskProfile: RiskProfile
  onRiskProfileChange: (profile: RiskProfile) => void
  networkFailure: boolean
  onNetworkFailureChange: (value: boolean) => void
}) {
  const positive = asset.change >= 0

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="asset-select" className="text-xs text-muted-foreground">
          Asset
        </Label>
        <Select value={symbol} onValueChange={(v) => onSymbolChange(v as AssetSymbol)}>
          <SelectTrigger id="asset-select" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ASSETS.map((a) => (
              <SelectItem key={a.symbol} value={a.symbol}>
                <span className="font-medium">{a.symbol}</span>
                <span className="text-muted-foreground">{a.name}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1 rounded-lg bg-surface p-3 ring-1 ring-border">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-lg font-semibold tabular-nums leading-none">
            ₹{asset.price.toLocaleString("en-IN")}
          </span>
          <span
            className={
              positive
                ? "text-xs font-medium tabular-nums text-success"
                : "text-xs font-medium tabular-nums text-destructive"
            }
          >
            {positive ? "+" : ""}
            {asset.change.toFixed(2)} ({positive ? "+" : ""}
            {asset.changePercent.toFixed(2)}%)
          </span>
        </div>
        <SparklineChart data={asset.sparkline} positive={positive} />
        <span className="text-[11px] text-muted-foreground">
          {networkFailure ? "Showing last cached price" : `Updated ${asset.lastUpdated}`}
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs text-muted-foreground">Risk profile</Label>
        <ToggleGroup
          variant="outline"
          spacing={0}
          value={[riskProfile]}
          onValueChange={(v) => {
            const value = v[0]
            if (value) onRiskProfileChange(value as RiskProfile)
          }}
          className="w-full"
        >
          <ToggleGroupItem value="conservative" className="flex-1">
            Conservative
          </ToggleGroupItem>
          <ToggleGroupItem value="aggressive" className="flex-1">
            Aggressive
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-lg bg-surface p-3 ring-1 ring-border">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="network-failure" className="text-xs font-medium">
            Simulate network failure
          </Label>
          <span className="text-[11px] text-muted-foreground">
            Preview degraded connectivity handling
          </span>
        </div>
        <Switch
          id="network-failure"
          checked={networkFailure}
          onCheckedChange={onNetworkFailureChange}
        />
      </div>
    </div>
  )
}
