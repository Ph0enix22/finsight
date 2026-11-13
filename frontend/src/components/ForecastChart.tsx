import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts'

import { Skeleton } from '@/components/ui/Skeleton'
import { formatDate, formatINR } from '@/lib/format'
import type { BalancePoint } from '@/lib/ledger'
import type { ForecastPoint } from '@/lib/runwayStub'

interface ChartRow {
  date: string
  actual?: number
  median?: number
  p10?: number
  bandWidth?: number
  scenario?: number
}

interface ForecastChartProps {
  actual: BalancePoint[]
  forecast: ForecastPoint[]
  nextInflowDate: string
  scenario?: { date: string; value: number }[]
}

function buildRows(
  actual: BalancePoint[],
  forecast: ForecastPoint[],
  scenario?: { date: string; value: number }[],
): ChartRow[] {
  const byDate = new Map<string, ChartRow>()
  for (const point of actual) {
    const date = point.date.slice(0, 10)
    byDate.set(date, { ...byDate.get(date), date, actual: point.balance })
  }
  for (const point of forecast) {
    byDate.set(point.date, {
      ...byDate.get(point.date),
      date: point.date,
      median: point.median,
      p10: point.p10,
      bandWidth: point.p90 - point.p10,
    })
  }
  for (const point of scenario ?? []) {
    byDate.set(point.date, { ...byDate.get(point.date), date: point.date, scenario: point.value })
  }
  return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date))
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null
  return (
    <div className="rounded-input bg-card px-3 py-2 text-micro shadow-md">
      <p className="font-medium text-foreground">{formatDate(label)}</p>
      {payload
        .filter((entry) => entry.dataKey === 'actual' || entry.dataKey === 'median')
        .map((entry) => (
          <p key={entry.dataKey} className="text-muted-foreground">
            {entry.dataKey === 'actual' ? 'Balance' : 'Expected'}: {formatINR(entry.value)}
          </p>
        ))}
    </div>
  )
}

export function ForecastChart({ actual, forecast, nextInflowDate, scenario }: ForecastChartProps) {
  const rows = buildRows(actual, forecast, scenario)

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tickFormatter={(value: string) => formatDate(value)}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            minTickGap={32}
          />
          <Tooltip content={<ChartTooltip />} />
          <ReferenceLine
            x={nextInflowDate}
            stroke="var(--good)"
            strokeDasharray="4 4"
            label={{ value: 'Inflow', position: 'insideTopRight', fill: 'var(--good)', fontSize: 11 }}
          />
          <Area dataKey="p10" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
          <Area
            dataKey="bandWidth"
            stackId="band"
            stroke="none"
            fill="var(--muted-foreground)"
            fillOpacity={0.15}
            isAnimationActive={false}
          />
          <Line
            dataKey="median"
            stroke="var(--muted-foreground)"
            strokeDasharray="4 3"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          {scenario && (
            <Line
              dataKey="scenario"
              stroke="var(--scenario)"
              strokeDasharray="4 3"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          )}
          <Line
            dataKey="actual"
            stroke="var(--primary)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ForecastChartSkeleton() {
  return <Skeleton className="h-48 w-full" />
}
