"use client"

import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts"

export function SparklineChart({
  data,
  positive,
}: {
  data: number[]
  positive: boolean
}) {
  const chartData = data.map((value, index) => ({ index, value }))
  const colorVar = positive ? "var(--success)" : "var(--destructive)"

  return (
    <div className="h-14 w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="sparklineFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colorVar} stopOpacity={0.35} />
              <stop offset="100%" stopColor={colorVar} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis domain={["dataMin", "dataMax"]} hide />
          <Area
            type="monotone"
            dataKey="value"
            stroke={colorVar}
            strokeWidth={1.75}
            fill="url(#sparklineFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
