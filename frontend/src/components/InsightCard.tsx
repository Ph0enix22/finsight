import type { ReactNode } from 'react'

import { Skeleton } from '@/components/ui/Skeleton'

interface InsightCardProps {
  headline: string
  subcopy: string
  receipt?: ReactNode
}

export function InsightCard({ headline, subcopy, receipt }: InsightCardProps) {
  return (
    <div className="flex h-full w-full shrink-0 flex-col gap-2 snap-start rounded-card bg-card p-5">
      <p className="text-body font-medium text-foreground">{headline}</p>
      <p className="text-small text-muted-foreground">{subcopy}</p>
      {receipt && <div className="mt-1">{receipt}</div>}
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
