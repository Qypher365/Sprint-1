import { cn } from "@/lib/utils"
import type { Signal } from "@/lib/mock-data"

const SIGNAL_STROKE: Record<Signal, string> = {
  BULLISH: "var(--success)",
  BEARISH: "var(--destructive)",
  NEUTRAL: "var(--warning)",
}

export function ConfidenceGauge({
  confidence,
  signal,
  size = 128,
}: {
  confidence: number
  signal: Signal
  size?: number
}) {
  const strokeWidth = 10
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - confidence / 100)

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Confidence ${confidence} percent, ${signal.toLowerCase()}`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={SIGNAL_STROKE[signal]}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-2xl font-semibold leading-none tabular-nums")}>
          {confidence}%
        </span>
        <span className="mt-1 text-[11px] text-muted-foreground">confidence</span>
      </div>
    </div>
  )
}
