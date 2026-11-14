import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { ForecastChart, ForecastChartSkeleton } from '@/components/ForecastChart'
import { ScenarioForm } from '@/components/ScenarioForm'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { api } from '@/lib/api'
import { firstOfMonth } from '@/lib/date'
import { balanceHistory } from '@/lib/ledger'
import {
  defaultScenarioState,
  scenarioKindFromPrompt,
  scenarioStateFromPrefill,
  type ScenarioFormState,
  type ScenarioPrefill,
} from '@/lib/scenario'
import { useSession } from '@/lib/session'
import { CircleSlash2 } from 'lucide-react'

interface WhatIfNavState {
  prompt?: string
  prefill?: ScenarioPrefill
}

function initialScenarioState(asOfDate: string, navState: WhatIfNavState | null): ScenarioFormState {
  if (navState?.prefill) return scenarioStateFromPrefill(navState.prefill, asOfDate)
  if (navState?.prompt) return defaultScenarioState(scenarioKindFromPrompt(navState.prompt), asOfDate)
  return defaultScenarioState('buy', asOfDate)
}

export function WhatIf() {
  const { session } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const navState = (location.state as WhatIfNavState | null) ?? null
  const [scenarioForecast, setScenarioForecast] = useState<{ date: string; value: number }[] | undefined>()

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
    return (
      <div className="pt-6">
        <ForecastChartSkeleton />
      </div>
    )
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

  const runway = runwayQuery.data

  if (runway.recurring_series.length === 0 && txnsQuery.data.length === 0) {
    return (
      <EmptyState
        icon={CircleSlash2}
        heading="Nothing to simulate yet"
        subcopy="Once you have some activity, you can play out what a purchase, EMI, or new goal would do to your balance."
      />
    )
  }

  const actual = balanceHistory(txnsQuery.data)

  return (
    <div className="pt-4">
      <p className="font-heading text-h2 font-semibold text-foreground">What if...</p>
      <p className="mt-0.5 text-small text-muted-foreground">
        Play out a scenario before you commit — nothing here touches your real balance.
      </p>

      <div className="mt-5">
        <ForecastChart
          actual={actual}
          forecast={runway.forecast}
          asOfDate={asOfDate}
          nextInflowDate={runway.next_inflow_date}
          scenario={scenarioForecast}
        />
      </div>

      <div className="mt-5">
        <ScenarioForm
          accountId={session.accountId}
          userId={session.userId}
          asOfDate={asOfDate}
          baseline={runway}
          recurringSeries={runway.recurring_series}
          initialState={initialScenarioState(asOfDate, navState)}
          onScenarioForecast={setScenarioForecast}
          onDone={() => navigate('/today')}
        />
      </div>
    </div>
  )
}
