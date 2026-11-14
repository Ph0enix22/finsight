import { AlertTriangle, ShieldCheck } from 'lucide-react'

import { Skeleton } from '@/components/ui/Skeleton'
import { daysBetween } from '@/lib/date'
import { formatDate, formatINR } from '@/lib/format'
import { useCountUp } from '@/lib/useCountUp'

type RunOutRisk = 'low' | 'watch' | 'risk'

function riskBucket(pRunOut: number): RunOutRisk {
  if (pRunOut < 0.1) return 'low'
  if (pRunOut < 0.5) return 'watch'
  return 'risk'
}

const COUNT_UP_MS = 700
const RUNWAY_WINDOW_DAYS = 30

const RISK_COPY: Record<RunOutRisk, { label: string; className: string }> = {
  low: { label: 'Low risk', className: 'bg-good/10 text-good' },
  watch: { label: 'Worth a look', className: 'bg-watch/10 text-watch' },
  risk: { label: 'Tight month', className: 'bg-risk/10 text-risk' },
}

interface SafeToSpendCardProps {
  safeToSpendPerDayPaise: number
  asOfDate: string
  nextInflowDate: string
  pRunOut: number
}

export function SafeToSpendCard({
  safeToSpendPerDayPaise,
  asOfDate,
  nextInflowDate,
  pRunOut,
}: SafeToSpendCardProps) {
  const animated = useCountUp(safeToSpendPerDayPaise, COUNT_UP_MS)
  const daysRemaining = Math.max(daysBetween(asOfDate, nextInflowDate), 0)
  const elapsedFraction = Math.min(
    Math.max(1 - daysRemaining / RUNWAY_WINDOW_DAYS, 0),
    1,
  )
  const pRunOutRisk = riskBucket(pRunOut)
  const risk = RISK_COPY[pRunOutRisk]
  const RiskIcon = pRunOutRisk === 'low' ? ShieldCheck : AlertTriangle

  return (
    <div className="rounded-card bg-card p-6">
      <p className="text-small text-muted-foreground">Safe to spend</p>
      <p className="mt-1 font-heading text-hero font-bold tabular-nums text-foreground">
        {formatINR(animated)}
        <span className="ml-1 text-h2 font-medium text-muted-foreground">/day</span>
      </p>
      <p className="mt-1 text-small text-muted-foreground">
        Until {formatDate(nextInflowDate)} · {daysRemaining} day{daysRemaining === 1 ? '' : 's'} to go
      </p>

      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${elapsedFraction * 100}%` }}
        />
      </div>

      <div className={`mt-4 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-micro font-medium ${risk.className}`}>
        <RiskIcon size={14} />
        <span>
          {risk.label} · {Math.round(pRunOut * 100)}% chance of running out
        </span>
      </div>
    </div>
  )
}

export function SafeToSpendCardSkeleton() {
  return (
    <div className="rounded-card bg-card p-6">
      <Skeleton className="h-4 w-28" />
      <Skeleton className="mt-2 h-10 w-44" />
      <Skeleton className="mt-2 h-4 w-36" />
      <Skeleton className="mt-4 h-1.5 w-full" />
      <Skeleton className="mt-4 h-6 w-40 rounded-full" />
    </div>
  )
}
