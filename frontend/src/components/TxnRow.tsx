import { MoreHorizontal } from 'lucide-react'
import { useRef } from 'react'

import { Skeleton } from '@/components/ui/Skeleton'
import { formatDate, formatINR, formatTime, merchantInitial } from '@/lib/format'
import { CATEGORY_LABELS } from '@/lib/types'
import type { Transaction } from '@/lib/types'

const LONG_PRESS_MS = 500
const LOW_CONFIDENCE_THRESHOLD = 0.6

interface TxnRowProps {
  txn: Transaction
  showDate?: boolean
  onRequestRecategorise?: (txn: Transaction) => void
}

export function TxnRow({ txn, showDate = false, onRequestRecategorise }: TxnRowProps) {
  const pressTimer = useRef<number | null>(null)

  const startPress = () => {
    if (!onRequestRecategorise) return
    pressTimer.current = window.setTimeout(() => onRequestRecategorise(txn), LONG_PRESS_MS)
  }
  const cancelPress = () => {
    if (pressTimer.current != null) {
      window.clearTimeout(pressTimer.current)
      pressTimer.current = null
    }
  }

  const name = txn.merchant_name ?? txn.raw_text.slice(0, 24)
  const isLowConfidence =
    txn.category_confidence != null && txn.category_confidence < LOW_CONFIDENCE_THRESHOLD

  return (
    <div
      className="group relative flex items-center gap-3 py-3 select-none"
      onPointerDown={startPress}
      onPointerUp={cancelPress}
      onPointerLeave={cancelPress}
    >
      <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted font-heading text-small font-semibold text-foreground">
        {merchantInitial(name)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-body font-medium text-foreground">{name}</p>
          {isLowConfidence && (
            <span
              className="size-1.5 shrink-0 rounded-full bg-watch"
              title="Low-confidence category — tap to confirm"
            />
          )}
        </div>
        <p className="text-micro text-muted-foreground">
          {txn.category ? CATEGORY_LABELS[txn.category] : 'Uncategorised'}
          {' · '}
          {showDate ? formatDate(txn.ts) : formatTime(txn.ts)}
        </p>
      </div>
      <p
        className={`shrink-0 text-right text-body font-medium tabular-nums transition-[padding-right] ${
          onRequestRecategorise ? 'group-hover:pr-8 group-focus-within:pr-8' : ''
        } ${txn.direction === 'CR' ? 'text-good' : 'text-foreground'}`}
      >
        {txn.direction === 'CR' ? '+' : ''}
        {formatINR(txn.amount_paise)}
      </p>
      {onRequestRecategorise && (
        <button
          type="button"
          aria-label={`Recategorise ${name}`}
          onClick={() => onRequestRecategorise(txn)}
          className="absolute right-0 top-1/2 flex size-8 shrink-0 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
        >
          <MoreHorizontal size={18} />
        </button>
      )}
    </div>
  )
}

export function TxnRowSkeleton() {
  return (
    <div className="flex items-center gap-3 py-3">
      <Skeleton className="size-9 shrink-0 rounded-full" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
      <Skeleton className="h-4 w-16 shrink-0" />
    </div>
  )
}
