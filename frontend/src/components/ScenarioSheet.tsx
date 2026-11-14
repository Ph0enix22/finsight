import { useQuery } from '@tanstack/react-query'

import { BottomSheet } from '@/components/ui/BottomSheet'
import { ScenarioForm } from '@/components/ScenarioForm'
import { api } from '@/lib/api'
import { defaultScenarioState, scenarioStateFromPrefill, type ScenarioPrefill } from '@/lib/scenario'

interface ScenarioSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  accountId: number
  userId: number
  asOfDate: string
  prefill?: ScenarioPrefill
}

/** Quick-access wrapper around ScenarioForm for TxnRow / Activity, where a full
 * screen nav would interrupt the list the user is scanning. */
export function ScenarioSheet({ open, onOpenChange, accountId, userId, asOfDate, prefill }: ScenarioSheetProps) {
  const runwayQuery = useQuery({
    queryKey: ['runway', accountId],
    queryFn: () => api.getRunway(accountId),
    enabled: open,
  })

  const initialState = prefill
    ? scenarioStateFromPrefill(prefill, asOfDate)
    : defaultScenarioState('buy', asOfDate)

  return (
    <BottomSheet open={open} onOpenChange={onOpenChange} title="What if...">
      {runwayQuery.data ? (
        <ScenarioForm
          accountId={accountId}
          userId={userId}
          asOfDate={asOfDate}
          baseline={runwayQuery.data}
          recurringSeries={runwayQuery.data.recurring_series}
          initialState={initialState}
          onScenarioForecast={() => {}}
          onDone={() => onOpenChange(false)}
        />
      ) : (
        <p className="py-8 text-center text-small text-muted-foreground">Loading your forecast…</p>
      )}
    </BottomSheet>
  )
}
