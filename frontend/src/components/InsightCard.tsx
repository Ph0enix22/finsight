import type { ReactNode } from 'react'

import { Skeleton } from '@/components/ui/Skeleton'

interface InsightCardProps {
  headline: string
  subcopy: string
  receipt?: ReactNode
  action?: { label: string; onClick: () => void }
}

export function InsightCard({ headline, subcopy, receipt, action }: InsightCardProps) {
  return (
    <div className="flex h-full w-full shrink-0 flex-col gap-2 snap-start rounded-card bg-card p-5">
      <p className="text-body font-medium text-foreground">{headline}</p>
      <p className="text-small text-muted-foreground">{subcopy}</p>
      {(receipt || action) && (
        <div className="mt-1 flex items-center gap-2">
          {receipt}
          {action && (
            <button
              type="button"
              onClick={action.onClick}
              className="inline-flex min-h-8 items-center rounded-full border border-scenario/40 px-3 text-micro font-medium text-scenario hover:bg-scenario/10"
            >
              {action.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export function InsightCardSkeleton() {
  return (
    <div className="flex h-full w-full shrink-0 flex-col gap-2 rounded-card bg-card p-5">
      <Skeleton className="h-4 w-4/5" />
      <Skeleton className="h-3 w-3/5" />
      <Skeleton className="mt-1 h-6 w-20 rounded-full" />
    </div>
  )
}
