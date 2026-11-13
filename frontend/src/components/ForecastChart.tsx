import {
  Area,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Skeleton } from '@/components/ui/Skeleton'
import { toISTDateString } from '@/lib/date'
import { formatDate, formatINR, formatINRShort } from '@/lib/format'
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
  asOfDate: string
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
    const date = toISTDateString(point.date)
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

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { dataKey: string; value: number }[]
  label?: string
}) {
  if (!active || !payload?.length || !label) return null
  return (
    <div className="rounded-input bg-card px-3 py-2 text-micro shadow-md">
      <p className="font-medium text-foreground">{formatDate(label)}</p>
      {payload
        .filter((entry) => entry.dataKey === 'actual' || entry.dataKey === 'median')
        .map((entry) => (
          <p key={entry.dataKey} className="text-muted-foreground">
            {entry.dataKey === 'actual' ? 'Balance' : 'Likely'}: {formatINR(entry.value)}
          </p>
        ))}
    </div>
  )
}

const LEGEND_ITEMS = [
  { label: 'Actual', swatch: 'h-0.5 w-3 rounded-full bg-primary' },
  { label: 'Likely', swatch: 'h-0.5 w-3 rounded-full border-t border-dashed border-muted-foreground' },
  { label: 'Range', swatch: 'h-2.5 w-3 rounded-[2px] bg-muted-foreground/20' },
]

export function ForecastChart({ actual, forecast, asOfDate, nextInflowDate, scenario }: ForecastChartProps) {
  const rows = buildRows(actual, forecast, scenario)
  const lastActual = actual[actual.length - 1]
  const lastForecast = forecast[forecast.length - 1]
  const maxValue = Math.max(
    ...rows.map((r) => Math.max(r.actual ?? 0, (r.median ?? 0) + (r.bandWidth ?? 0) / 2, r.p10 ?? 0)),
  )

  return (
    <div>
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 12, right: 44, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="date"
              tickFormatter={(value: string) => formatDate(value)}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              domain={[0, Math.ceil((maxValue * 1.08) / 100) * 100]}
              tickFormatter={(value: number) => formatINRShort(value)}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickCount={3}
              width={40}
            />
            <Tooltip content={<ChartTooltip />} />

            <ReferenceLine x={asOfDate} stroke="var(--muted-foreground)" strokeDasharray="2 3" />
            <ReferenceLine x={nextInflowDate} stroke="var(--good)" strokeDasharray="2 3" />

            <Area dataKey="p10" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
            <Area
              dataKey="bandWidth"
              stackId="band"
              stroke="none"
              fill="var(--muted-foreground)"
              fillOpacity={0.14}
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
            <Line dataKey="actual" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />

            {lastActual && (
              <ReferenceDot
                x={toISTDateString(lastActual.date)}
                y={lastActual.balance}
                r={3}
                fill="var(--primary)"
                stroke="var(--card)"
                strokeWidth={2}
                label={{
                  value: formatINR(lastActual.balance),
                  position: 'top',
                  fill: 'var(--primary)',
                  fontSize: 11,
                  fontWeight: 600,
                }}
              />
            )}
            {lastForecast && (
              <ReferenceDot
                x={lastForecast.date}
                y={lastForecast.median}
                r={3}
                fill="var(--muted-foreground)"
                stroke="var(--card)"
                strokeWidth={2}
                label={{
                  value: formatINR(lastForecast.median),
                  position: 'top',
                  fill: 'var(--muted-foreground)',
                  fontSize: 11,
                  fontWeight: 600,
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex items-center justify-center gap-4">
        {LEGEND_ITEMS.map((item) => (
          <span key={item.label} className="flex items-center gap-1.5 text-micro text-muted-foreground">
            <span className={item.swatch} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  )
}

export function ForecastChartSkeleton() {
  return <Skeleton className="h-48 w-full" />
}
