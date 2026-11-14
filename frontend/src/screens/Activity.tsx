import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LayoutList, PieChart as PieChartIcon, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { CategoryDonut, type CategoryTotal } from '@/components/CategoryDonut'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { FilterChips } from '@/components/FilterChips'
import { TxnRow, TxnRowSkeleton } from '@/components/TxnRow'
import { BottomSheet } from '@/components/ui/BottomSheet'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import { toISTDateString } from '@/lib/date'
import { formatDate, formatINR } from '@/lib/format'
import { useSession } from '@/lib/session'
import { CATEGORIES, CATEGORY_LABELS, type Category, type Transaction } from '@/lib/types'

export function Activity() {
  const { session } = useSession()
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<Category | null>(null)
  const [view, setView] = useState<'list' | 'donut'>('list')
  const [recategoriseTarget, setRecategoriseTarget] = useState<Transaction | null>(null)

  const healthQuery = useQuery({ queryKey: ['health'], queryFn: api.health })
  const asOfDate = healthQuery.data?.as_of_date

  const queryKey = ['transactions', session?.accountId, asOfDate]
  const txnsQuery = useQuery({
    queryKey,
    queryFn: () => api.listTransactions({ accountId: session!.accountId, to: asOfDate, limit: 300 }),
    enabled: session != null && asOfDate != null,
  })

  const categoriesPresent = useMemo(() => {
    if (!txnsQuery.data) return []
    const present = new Set(txnsQuery.data.map((t) => t.category).filter((c): c is Category => c != null))
    return CATEGORIES.filter((c) => present.has(c))
  }, [txnsQuery.data])

  const filtered = useMemo(() => {
    if (!txnsQuery.data) return []
    const needle = search.trim().toLowerCase()
    return txnsQuery.data.filter((t) => {
      if (activeCategory && t.category !== activeCategory) return false
      if (!needle) return true
      return (t.merchant_name ?? t.raw_text).toLowerCase().includes(needle)
    })
  }, [txnsQuery.data, search, activeCategory])

  const groups = useMemo(() => {
    const byDay = new Map<string, Transaction[]>()
    for (const txn of filtered) {
      const day = toISTDateString(txn.ts)
      const list = byDay.get(day) ?? []
      list.push(txn)
      byDay.set(day, list)
    }
    return Array.from(byDay.entries())
  }, [filtered])

  const donutData: CategoryTotal[] = useMemo(() => {
    const totals = new Map<Category, number>()
    for (const t of filtered) {
      if (t.direction !== 'DR' || t.category == null) continue
      totals.set(t.category, (totals.get(t.category) ?? 0) + t.amount_paise)
    }
    return Array.from(totals.entries())
      .map(([category, totalPaise]) => ({ category, totalPaise }))
      .sort((a, b) => b.totalPaise - a.totalPaise)
  }, [filtered])

  async function handleRecategorise(category: Category) {
    if (!recategoriseTarget) return
    const target = recategoriseTarget
    const previousCategory = target.category
    setRecategoriseTarget(null)
    const res = await api.recategorise(target.id, category)
    await queryClient.invalidateQueries({ queryKey })

    showToast(`Updated ${res.updated_count} similar transaction${res.updated_count === 1 ? '' : 's'}`, {
      label: 'Undo',
      onClick: () => {
        void Promise.all(
          res.txn_ids.map((id) => api.recategorise(id, previousCategory ?? 'shopping')),
        ).then(() => queryClient.invalidateQueries({ queryKey }))
      },
    })
  }

  if (!session) return null

  if (healthQuery.isLoading || txnsQuery.isLoading) {
    return (
      <div className="pt-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <TxnRowSkeleton key={i} />
        ))}
      </div>
    )
  }

  if (healthQuery.isError || txnsQuery.isError || !txnsQuery.data) {
    return (
      <ErrorState
        onRetry={() => {
          void healthQuery.refetch()
          void txnsQuery.refetch()
        }}
      />
    )
  }

  if (txnsQuery.data.length === 0) {
    return (
      <EmptyState
        icon={Search}
        heading="No transactions yet"
        subcopy="Once some activity comes in, it'll show up here as a ledger."
      />
    )
  }

  return (
    <div className="pt-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            size={16}
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search merchant"
            aria-label="Search merchant"
            className="min-h-11 w-full rounded-input border border-border bg-card pl-9 pr-3 text-small text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </div>
        <button
          type="button"
          aria-label={view === 'list' ? 'Show category breakdown' : 'Show list'}
          aria-pressed={view === 'donut'}
          onClick={() => setView((v) => (v === 'list' ? 'donut' : 'list'))}
          className="flex size-11 shrink-0 items-center justify-center rounded-input border border-border text-muted-foreground hover:text-foreground"
        >
          {view === 'list' ? <PieChartIcon size={18} /> : <LayoutList size={18} />}
        </button>
      </div>

      <div className="mt-3">
        <FilterChips categories={categoriesPresent} active={activeCategory} onChange={setActiveCategory} />
      </div>

      <div className="mt-2 border-t border-border">
        {view === 'donut' ? (
          donutData.length > 0 ? (
            <div className="py-6">
              <CategoryDonut data={donutData} />
            </div>
          ) : (
            <EmptyState icon={PieChartIcon} heading="Nothing to chart" subcopy="No spend matches this filter." />
          )
        ) : filtered.length === 0 ? (
          <EmptyState icon={Search} heading="No matches" subcopy="Try a different search term or category." />
        ) : (
          groups.map(([day, txns]) => {
            const dayTotal = txns.reduce(
              (sum, t) => sum + (t.direction === 'DR' ? t.amount_paise : -t.amount_paise),
              0,
            )
            return (
              <div key={day}>
                <div className="flex items-baseline justify-between pt-4 pb-1">
                  <p className="text-micro font-medium text-muted-foreground">{formatDate(day)}</p>
                  <p className="text-micro tabular-nums text-muted-foreground">{formatINR(dayTotal)}</p>
                </div>
                <div className="divide-y divide-border">
                  {txns.map((txn) => (
                    <TxnRow key={txn.id} txn={txn} onRequestRecategorise={setRecategoriseTarget} />
                  ))}
                </div>
              </div>
            )
          })
        )}
      </div>

      <BottomSheet
        open={recategoriseTarget != null}
        onOpenChange={(open) => !open && setRecategoriseTarget(null)}
        title={recategoriseTarget?.merchant_name ?? 'Recategorise'}
      >
        <button
          type="button"
          onClick={() => {
            if (!recategoriseTarget) return
            const txn = recategoriseTarget
            setRecategoriseTarget(null)
            navigate('/whatif', {
              state: {
                prompt: 'Simulate removing this',
                prefill: {
                  type: 'one_time_purchase',
                  amountPaise: txn.direction === 'DR' ? -txn.amount_paise : txn.amount_paise,
                },
              },
            })
          }}
          className="mb-3 w-full rounded-input border border-scenario/40 px-3 py-2.5 text-small font-medium text-scenario hover:bg-scenario/10"
        >
          Simulate removing this
        </button>
        <div className="grid grid-cols-2 gap-2 pb-4">
          {CATEGORIES.map((category) => (
            <button
              key={category}
              type="button"
              onClick={() => void handleRecategorise(category)}
              className={`rounded-input border px-3 py-2.5 text-small transition-colors ${
                recategoriseTarget?.category === category
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-foreground hover:border-primary'
              }`}
            >
              {CATEGORY_LABELS[category]}
            </button>
          ))}
        </div>
      </BottomSheet>
    </div>
  )
}
