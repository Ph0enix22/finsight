import { useQuery } from '@tanstack/react-query'
import { Inbox } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ForecastChart, ForecastChartSkeleton } from '@/components/ForecastChart'
import { InsightCard, InsightCardSkeleton } from '@/components/InsightCard'
import { ReceiptChip } from '@/components/ReceiptChip'
import { SafeToSpendCard, SafeToSpendCardSkeleton } from '@/components/SafeToSpendCard'
import { WhatIfBar } from '@/components/WhatIfBar'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { api } from '@/lib/api'
import { formatDateWithWeekday, formatINR, formatTime } from '@/lib/format'
import { firstOfMonth } from '@/lib/date'
import { balanceHistory } from '@/lib/ledger'
import { computeFoodUnderThresholdInsight, findKnownAnomaly } from '@/lib/insightsStub'
import { useSession } from '@/lib/session'

const CARD_COUNT = 2

const PERSONA_FIRST_NAMES: Record<string, string> = {
  aarav: 'Aarav',
  priya: 'Priya',
  fatima: 'Fatima',
  custom: 'there',
}

export function Today() {
  const { session } = useSession()
  const navigate = useNavigate()
  const [activeCard, setActiveCard] = useState(0)
  const cardsRef = useRef<HTMLDivElement | null>(null)

  function handleCardsScroll() {
    const el = cardsRef.current
    if (!el) return
    setActiveCard(Math.round(el.scrollLeft / el.clientWidth))
  }

  const healthQuery = useQuery({ queryKey: ['health'], queryFn: api.health })
  const asOfDate = healthQuery.data?.as_of_date

  const txnsQuery = useQuery({
    queryKey: ['transactions', 'this-month', session?.accountId, asOfDate],
    queryFn: () =>
      api.listTransactions({
        accountId: session!.accountId,
        from: firstOfMonth(asOfDate!),
        to: asOfDate,
        limit: 300,
      }),
    enabled: session != null && asOfDate != null,
  })

  const runwayQuery = useQuery({
    queryKey: ['runway', session?.accountId],
    queryFn: () => api.getRunway(session!.accountId),
    enabled: session != null,
  })

  if (!session) return null

  if (healthQuery.isLoading || txnsQuery.isLoading || runwayQuery.isLoading) {
    return <TodaySkeleton />
  }

  if (
    healthQuery.isError ||
    txnsQuery.isError ||
    runwayQuery.isError ||
    !asOfDate ||
    !txnsQuery.data ||
    !runwayQuery.data
  ) {
    return (
      <ErrorState
        onRetry={() => {
          void healthQuery.refetch()
          void txnsQuery.refetch()
          void runwayQuery.refetch()
        }}
      />
    )
  }

  const transactions = txnsQuery.data
  const runway = runwayQuery.data

  if (transactions.length === 0) {
    return (
      <EmptyState
        icon={Inbox}
        heading="No transactions yet"
        subcopy="Once some activity comes in, your safe-to-spend number and forecast will show up here."
      />
    )
  }

  const actual = balanceHistory(transactions)

  const foodInsight = computeFoodUnderThresholdInsight(transactions)
  const foodTxns = transactions.filter((t) => foodInsight.txnIds.includes(t.id))
  const anomalyTxn = findKnownAnomaly(transactions, session.personaKey)

  const monthlyInflowPaise = transactions
    .filter((t) => t.direction === 'CR')
    .reduce((sum, t) => sum + t.amount_paise, 0)
  const foodShareOfAllowance =
    monthlyInflowPaise > 0 ? Math.round((foodInsight.totalPaise / monthlyInflowPaise) * 100) : null
  const firstName = PERSONA_FIRST_NAMES[session.personaKey] ?? session.personaKey

  return (
    <div className="pt-4">
      <p className="font-heading text-h2 font-semibold text-foreground">Hi {firstName}</p>
      <p className="mt-0.5 text-small text-muted-foreground">{formatDateWithWeekday(asOfDate)}</p>

      <div className="mt-4">
        <SafeToSpendCard
          safeToSpendPerDayPaise={runway.safe_to_spend_per_day_paise}
          asOfDate={asOfDate}
          nextInflowDate={runway.next_inflow_date}
          pRunOut={runway.p_run_out}
        />
      </div>

      <div className="mt-6">
        <ForecastChart
          actual={actual}
          forecast={runway.forecast}
          asOfDate={asOfDate}
          nextInflowDate={runway.next_inflow_date}
        />
      </div>

      <div
        ref={cardsRef}
        onScroll={handleCardsScroll}
        className="-mx-4 mt-6 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1"
      >
        <div className="w-[calc(100%-24px)] shrink-0 snap-start">
          {foodInsight.count > 0 ? (
            <InsightCard
              headline={`${foodInsight.count} food orders this month, each under ₹200`}
              subcopy={
                foodShareOfAllowance != null
                  ? `Together ${formatINR(foodInsight.totalPaise)}, about ${foodShareOfAllowance}% of your monthly allowance.`
                  : `Together that's ${formatINR(foodInsight.totalPaise)} — mostly small, frequent orders.`
              }
              receipt={
                <ReceiptChip
                  label={`${formatINR(foodInsight.totalPaise)} · ${foodInsight.count} txns`}
                  sheetTitle="Food under ₹200"
                  formula={`${foodInsight.count} payments, avg ${formatINR(
                    Math.round(foodInsight.totalPaise / foodInsight.count),
                  )} each = ${formatINR(foodInsight.totalPaise)} total.`}
                  txns={foodTxns}
                />
              }
              action={{
                label: 'Simulate cutting half',
                onClick: () =>
                  navigate('/whatif', {
                    state: {
                      prompt: 'Cut my food orders in half',
                      prefill: { type: 'one_time_purchase', amountPaise: -Math.round(foodInsight.totalPaise / 2) },
                    },
                  }),
              }}
            />
          ) : (
            <InsightCard
              headline="No small food orders yet"
              subcopy="Once a few come in, they'll show up here."
            />
          )}
        </div>
        <div className="w-[calc(100%-24px)] shrink-0 snap-start">
          {anomalyTxn ? (
            <InsightCard
              headline={`${formatINR(anomalyTxn.amount_paise)} at ${formatTime(anomalyTxn.ts)} to a new merchant`}
              subcopy={`${anomalyTxn.merchant_name ?? 'This merchant'} hasn't shown up anywhere else in your history.`}
              receipt={
                <ReceiptChip
                  label="Review"
                  sheetTitle="Unusual charge"
                  formula="Flagged for being a one-off, first-time merchant."
                  txns={[anomalyTxn]}
                />
              }
            />
          ) : (
            <InsightCard
              headline="Nothing unusual this month"
              subcopy="We'll flag anything that looks out of place."
            />
          )}
        </div>
      </div>

      <div className="mt-2 flex items-center justify-center gap-1.5" aria-hidden="true">
        {Array.from({ length: CARD_COUNT }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 rounded-full transition-all ${
              i === activeCard ? 'w-4 bg-primary' : 'w-1.5 bg-border'
            }`}
          />
        ))}
      </div>

      <div className="h-[var(--whatif-h)]" aria-hidden="true" />
      <WhatIfBar />
    </div>
  )
}

function TodaySkeleton() {
  return (
    <div className="pt-4">
      <SafeToSpendCardSkeleton />
      <div className="mt-6">
        <ForecastChartSkeleton />
      </div>
      <div className="mt-6 flex gap-3">
        <InsightCardSkeleton />
        <InsightCardSkeleton />
      </div>
    </div>
  )
}
