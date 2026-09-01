import { cn } from "@/lib/utils"
import { TrendingUpIcon, TrendingDownIcon, MinusIcon } from "lucide-react"
import type { Signal } from "@/lib/mock-data"

const SIGNAL_CONFIG: Record<
  Signal,
  { label: string; icon: typeof TrendingUpIcon; className: string }
> = {
  BULLISH: {
    label: "Bullish",
    icon: TrendingUpIcon,
    className: "bg-success/15 text-success",
  },
  BEARISH: {
    label: "Bearish",
    icon: TrendingDownIcon,
    className: "bg-destructive/15 text-destructive",
  },
  NEUTRAL: {
    label: "Neutral",
    icon: MinusIcon,
    className: "bg-warning/15 text-warning",
  },
}

export function SignalBadge({
  signal,
  className,
}: {
  signal: Signal
  className?: string
}) {
  const config = SIGNAL_CONFIG[signal]
  const Icon = config.icon
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center gap-1 rounded-4xl px-2 py-0.5 text-xs font-medium",
        config.className,
        className
      )}
    >
      <Icon className="size-3" aria-hidden="true" />
      {config.label}
    </span>
  )
}

export function LiveDot({ className }: { className?: string }) {
  return (
    <span className={cn("relative flex size-1.5", className)}>
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75" />
      <span className="relative inline-flex size-1.5 rounded-full bg-success" />
    </span>
  )
}
