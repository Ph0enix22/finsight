import { useQuery } from '@tanstack/react-query'
import { Inbox } from 'lucide-react'

import { ForecastChart, ForecastChartSkeleton } from '@/components/ForecastChart'
import { InsightCard, InsightCardSkeleton } from '@/components/InsightCard'
import { ReceiptChip } from '@/components/ReceiptChip'
import { SafeToSpendCard, SafeToSpendCardSkeleton } from '@/components/SafeToSpendCard'
import { WhatIfBar } from '@/components/WhatIfBar'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { api } from '@/lib/api'
import { formatINR, formatTime } from '@/lib/format'
import { firstOfMonth } from '@/lib/date'
import { balanceHistory, safeToSpendPerDayPaise } from '@/lib/ledger'
import { computeFoodUnderThresholdInsight, findKnownAnomaly } from '@/lib/insightsStub'
import { getRunwayStub } from '@/lib/runwayStub'
import { useSession } from '@/lib/session'

const ACTUAL_WINDOW_POINTS = 20

export function Today() {
  const { session } = useSession()

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

  if (!session) return null

  if (healthQuery.isLoading || txnsQuery.isLoading) {
    return <TodaySkeleton />
  }

  if (healthQuery.isError || txnsQuery.isError || !asOfDate || !txnsQuery.data) {
    return (
      <ErrorState
        onRetry={() => {
          void healthQuery.refetch()
          void txnsQuery.refetch()
        }}
      />
    )
  }

  const transactions = txnsQuery.data

  if (transactions.length === 0) {
    return (
      <EmptyState
        icon={Inbox}
        heading="No transactions yet"
        subcopy="Once some activity comes in, your safe-to-spend number and forecast will show up here."
      />
    )
  }

  const currentBalancePaise = transactions.find((t) => t.balance_after_paise != null)?.balance_after_paise ?? 0
  const runway = getRunwayStub(asOfDate, currentBalancePaise)
  const safeToSpend = safeToSpendPerDayPaise(currentBalancePaise, asOfDate, runway.nextInflowDate)
  const actual = balanceHistory(transactions).slice(-ACTUAL_WINDOW_POINTS)

  const foodInsight = computeFoodUnderThresholdInsight(transactions)
  const foodTxns = transactions.filter((t) => foodInsight.txnIds.includes(t.id))
  const anomalyTxn = findKnownAnomaly(transactions, session.personaKey)

  return (
    <div className="pt-4">
      <SafeToSpendCard
        safeToSpendPerDayPaise={safeToSpend}
        asOfDate={asOfDate}
        nextInflowDate={runway.nextInflowDate}
        pRunOutRisk={runway.pRunOutRisk}
        pRunOutPercent={runway.pRunOutPercent}
      />

      <div className="mt-6">
        <ForecastChart actual={actual} forecast={runway.forecast} nextInflowDate={runway.nextInflowDate} />
      </div>

      <div className="-mx-4 mt-6 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1">
        <div className="w-[calc(100%-24px)] shrink-0 snap-start">
          {foodInsight.count > 0 ? (
            <InsightCard
              headline={`${foodInsight.count} food orders this month, each under ₹200`}
              subcopy={`Together that's ${formatINR(foodInsight.totalPaise)} — mostly small, frequent orders.`}
              receipt={
                <ReceiptChip
                  label={`${foodInsight.count} txns`}
                  sheetTitle="Food under ₹200"
                  formula={`${foodInsight.count} payments, avg ${formatINR(
                    Math.round(foodInsight.totalPaise / foodInsight.count),
                  )} each = ${formatINR(foodInsight.totalPaise)} total.`}
                  txns={foodTxns}
                />
              }
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
              headline={`A ${formatINR(anomalyTxn.amount_paise)} charge at ${formatTime(anomalyTxn.ts)}`}
              subcopy={`${anomalyTxn.merchant_name ?? 'This merchant'} hasn't shown up anywhere else in your history.`}
              receipt={
                <ReceiptChip
                  label="1 txn"
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
