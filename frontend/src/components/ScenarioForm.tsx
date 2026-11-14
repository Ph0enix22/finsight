import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { formatDate, formatINR } from '@/lib/format'
import {
  SCENARIO_KIND_LABELS,
  activeSubscriptions,
  buildScenarioEvents,
  defaultScenarioState,
  type BuyMode,
  type ScenarioFormState,
  type ScenarioKind,
} from '@/lib/scenario'
import type { ForecastOut, RecurringSeries, TwinSimulateResponse } from '@/lib/types'
import { useCountUp } from '@/lib/useCountUp'
import { useToast } from '@/components/ui/Toast'

const KIND_ORDER: ScenarioKind[] = ['buy', 'emi', 'trip', 'subscription', 'goal']
const BUY_MODE_LABELS: Record<BuyMode, string> = { now: 'Pay now', emi: 'EMI', save_up: 'Save up' }
const DEBOUNCE_MS = 400
const SIMULATE_ANIMATION_MS = 400

function paiseToRupeeInput(paise: number): string {
  return String(Math.round(Math.abs(paise) / 100))
}

function rupeeInputToPaise(value: string): number {
  const n = Number(value)
  return Number.isFinite(n) ? Math.round(n * 100) : 0
}

interface AmountFieldProps {
  label: string
  valuePaise: number
  onChange: (paise: number) => void
}

function AmountField({ label, valuePaise, onChange }: AmountFieldProps) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1 rounded-input border border-border bg-card px-3">
        <span className="text-small text-muted-foreground">₹</span>
        <input
          type="number"
          min={0}
          inputMode="numeric"
          value={paiseToRupeeInput(valuePaise)}
          onChange={(e) => onChange(rupeeInputToPaise(e.target.value))}
          className="min-h-11 w-full bg-transparent text-body tabular-nums text-foreground focus-visible:outline-none"
        />
      </div>
    </label>
  )
}

function DateField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (iso: string) => void
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-muted-foreground">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-11 rounded-input border border-border bg-card px-3 text-body text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      />
    </label>
  )
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (n: number) => void
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-muted-foreground">{label}</span>
      <input
        type="number"
        min={1}
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || 1)}
        className="min-h-11 rounded-input border border-border bg-card px-3 text-body tabular-nums text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      />
    </label>
  )
}

function SegmentedPills<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`min-h-8 rounded-full border px-3 text-micro font-medium transition-colors ${
            value === opt.value
              ? 'border-scenario bg-scenario/10 text-scenario'
              : 'border-border text-muted-foreground hover:border-scenario/40'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

interface MetricPairProps {
  label: string
  baselinePaise: number
  scenarioPaise: number
  animate: boolean
}

function MetricPair({ label, baselinePaise, scenarioPaise, animate }: MetricPairProps) {
  const animated = useCountUp(animate ? scenarioPaise : baselinePaise, animate ? SIMULATE_ANIMATION_MS : 0)
  const delta = scenarioPaise - baselinePaise
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-small text-muted-foreground">{label}</span>
      <div className="text-right">
        <p className="font-heading text-h2 tabular-nums text-foreground">{formatINR(animated)}</p>
        {delta !== 0 && (
          <p className={`text-micro tabular-nums ${delta > 0 ? 'text-good' : 'text-risk'}`}>
            {delta > 0 ? '+' : ''}
            {formatINR(delta)} vs today
          </p>
        )}
      </div>
    </div>
  )
}

function RiskPair({ label, baseline, scenario, animate }: { label: string; baseline: number; scenario: number; animate: boolean }) {
  const target = Math.round((animate ? scenario : baseline) * 100)
  const animated = useCountUp(target, animate ? SIMULATE_ANIMATION_MS : 0)
  const deltaPct = Math.round((scenario - baseline) * 100)
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-small text-muted-foreground">{label}</span>
      <div className="text-right">
        <p className="font-heading text-h2 tabular-nums text-foreground">{animated}%</p>
        {deltaPct !== 0 && (
          <p className={`text-micro tabular-nums ${deltaPct <= 0 ? 'text-good' : 'text-risk'}`}>
            {deltaPct > 0 ? '+' : ''}
            {deltaPct}pt vs today
          </p>
        )}
      </div>
    </div>
  )
}

interface ScenarioFormProps {
  accountId: number
  userId: number
  asOfDate: string
  baseline: ForecastOut
  recurringSeries: RecurringSeries[]
  initialState: ScenarioFormState
  onScenarioForecast: (forecast: { date: string; value: number }[] | undefined) => void
  onDone: () => void
}

export function ScenarioForm({
  accountId,
  userId,
  asOfDate,
  baseline,
  recurringSeries,
  initialState,
  onScenarioForecast,
  onDone,
}: ScenarioFormProps) {
  const { showToast } = useToast()
  const [state, setState] = useState<ScenarioFormState>(initialState)
  const [result, setResult] = useState<TwinSimulateResponse | null>(null)
  const [isSimulating, setIsSimulating] = useState(false)
  const [simulateError, setSimulateError] = useState(false)
  const [savingPlan, setSavingPlan] = useState(false)

  const subscriptions = activeSubscriptions(recurringSeries)
  const stateKey = JSON.stringify(state)
  const build = buildScenarioEvents(state)
  const hasEvents = build.events.length > 0
  const effectiveResult = hasEvents ? result : null

  useEffect(() => {
    if (!hasEvents) {
      onScenarioForecast(undefined)
      return
    }
    const handle = window.setTimeout(() => {
      setIsSimulating(true)
      setSimulateError(false)
      api
        .twinSimulate({
          account_id: accountId,
          events: build.events,
          goal_target_amount_paise: build.goalTargetAmountPaise,
        })
        .then((res) => {
          setResult(res)
          onScenarioForecast(res.scenario.forecast.map((p) => ({ date: p.date, value: p.median })))
        })
        .catch(() => setSimulateError(true))
        .finally(() => setIsSimulating(false))
    }, DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateKey, accountId])

  function switchKind(kind: ScenarioKind) {
    setState(defaultScenarioState(kind, asOfDate))
  }

  const canMakePlan = build.goalTargetAmountPaise != null

  async function handleMakePlan() {
    if (build.goalTargetAmountPaise == null) return
    setSavingPlan(true)
    try {
      const targetDate = state.kind === 'buy' ? state.date : state.kind === 'goal' ? state.targetDate : asOfDate
      await api.createGoal({
        user_id: userId,
        name: SCENARIO_KIND_LABELS[state.kind],
        target_amount_paise: build.goalTargetAmountPaise,
        target_date: targetDate,
      })
      showToast('Plan saved to your goals')
      onDone()
    } catch {
      showToast('Could not save that plan — try again')
    } finally {
      setSavingPlan(false)
    }
  }

  return (
    <div className="flex flex-col gap-5 pb-6">
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {KIND_ORDER.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => switchKind(kind)}
            className={`shrink-0 rounded-full border px-3.5 py-2 text-micro font-medium transition-colors ${
              state.kind === kind
                ? 'border-scenario bg-scenario/10 text-scenario'
                : 'border-border text-muted-foreground hover:border-scenario/40'
            }`}
          >
            {SCENARIO_KIND_LABELS[kind]}
          </button>
        ))}
      </div>

      {state.kind === 'buy' && (
        <div className="flex flex-col gap-3">
          <AmountField
            label={state.isReduction ? 'Amount saved' : 'Amount'}
            valuePaise={state.amountPaise}
            onChange={(amountPaise) => setState({ ...state, amountPaise })}
          />
          {!state.isReduction && (
            <SegmentedPills
              options={(['now', 'emi', 'save_up'] as BuyMode[]).map((m) => ({ value: m, label: BUY_MODE_LABELS[m] }))}
              value={state.mode}
              onChange={(mode) => setState({ ...state, mode })}
            />
          )}
          {state.mode === 'emi' && (
            <NumberField
              label="Months"
              value={state.emiMonths}
              onChange={(emiMonths) => setState({ ...state, emiMonths })}
            />
          )}
          <DateField
            label={state.mode === 'save_up' ? 'Target date' : 'Date'}
            value={state.date}
            onChange={(date) => setState({ ...state, date })}
          />
        </div>
      )}

      {state.kind === 'emi' && (
        <div className="flex flex-col gap-3">
          <AmountField
            label="Total amount"
            valuePaise={state.amountPaise}
            onChange={(amountPaise) => setState({ ...state, amountPaise })}
          />
          <NumberField label="Months" value={state.months} onChange={(months) => setState({ ...state, months })} />
          <DateField label="Start date" value={state.startDate} onChange={(startDate) => setState({ ...state, startDate })} />
        </div>
      )}

      {state.kind === 'trip' && (
        <div className="flex flex-col gap-3">
          <AmountField
            label="Budget"
            valuePaise={state.amountPaise}
            onChange={(amountPaise) => setState({ ...state, amountPaise })}
          />
          <div className="grid grid-cols-2 gap-3">
            <DateField label="From" value={state.startDate} onChange={(startDate) => setState({ ...state, startDate })} />
            <DateField label="To" value={state.endDate} onChange={(endDate) => setState({ ...state, endDate })} />
          </div>
        </div>
      )}

      {state.kind === 'subscription' && (
        <div className="flex flex-col gap-3">
          <SegmentedPills
            options={[
              { value: 'cancel', label: 'Cancel one' },
              { value: 'add', label: 'Add new' },
            ]}
            value={state.mode}
            onChange={(mode) => setState({ ...state, mode })}
          />
          {state.mode === 'cancel' ? (
            subscriptions.length === 0 ? (
              <p className="text-small text-muted-foreground">No recurring subscriptions detected yet.</p>
            ) : (
              <div className="flex flex-col gap-1.5">
                {subscriptions.map((sub) => (
                  <button
                    key={sub.merchant_id}
                    type="button"
                    onClick={() =>
                      setState({
                        ...state,
                        merchantId: sub.merchant_id,
                        amountPaise: sub.typical_amount_paise,
                      })
                    }
                    className={`flex items-center justify-between rounded-input border px-3 py-2.5 text-left text-small transition-colors ${
                      state.merchantId === sub.merchant_id
                        ? 'border-scenario bg-scenario/10'
                        : 'border-border hover:border-scenario/40'
                    }`}
                  >
                    <span className="text-foreground">{sub.merchant_name ?? 'Unknown merchant'}</span>
                    <span className="tabular-nums text-muted-foreground">{formatINR(sub.typical_amount_paise)}</span>
                  </button>
                ))}
              </div>
            )
          ) : (
            <>
              <AmountField
                label="Amount per cycle"
                valuePaise={state.amountPaise}
                onChange={(amountPaise) => setState({ ...state, amountPaise })}
              />
              <NumberField
                label="Every N days"
                value={state.periodDays}
                onChange={(periodDays) => setState({ ...state, periodDays })}
              />
              <DateField label="First charge" value={state.nextDue} onChange={(nextDue) => setState({ ...state, nextDue })} />
            </>
          )}
        </div>
      )}

      {state.kind === 'goal' && (
        <div className="flex flex-col gap-3">
          <AmountField
            label="Target amount"
            valuePaise={state.targetAmountPaise}
            onChange={(targetAmountPaise) => setState({ ...state, targetAmountPaise })}
          />
          <DateField
            label="Target date"
            value={state.targetDate}
            onChange={(targetDate) => setState({ ...state, targetDate })}
          />
        </div>
      )}

      <div className="rounded-card bg-card p-4">
        {simulateError ? (
          <p className="py-4 text-center text-small text-muted-foreground">
            Could not simulate that scenario. Try adjusting the numbers.
          </p>
        ) : (
          <div className="divide-y divide-border">
            <MetricPair
              label="Safe to spend / day"
              baselinePaise={baseline.safe_to_spend_per_day_paise}
              scenarioPaise={effectiveResult?.scenario.safe_to_spend_per_day_paise ?? baseline.safe_to_spend_per_day_paise}
              animate={effectiveResult != null && !isSimulating}
            />
            <RiskPair
              label="Chance of running out"
              baseline={baseline.p_run_out}
              scenario={effectiveResult?.scenario.p_run_out ?? baseline.p_run_out}
              animate={effectiveResult != null && !isSimulating}
            />
            {effectiveResult?.goal_delay_days != null && (
              <div className="flex items-center justify-between py-2">
                <span className="text-small text-muted-foreground">Goal reached</span>
                <span className="text-small font-medium text-foreground">
                  {effectiveResult.goal_delay_days === 0
                    ? 'same time'
                    : effectiveResult.goal_delay_days > 0
                      ? `${effectiveResult.goal_delay_days} days later`
                      : `${Math.abs(effectiveResult.goal_delay_days)} days sooner`}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <p className="text-center text-micro text-muted-foreground">
        Compared against your forecast as of {formatDate(asOfDate)}.
      </p>

      <div className="flex gap-3">
        <Button variant="outline" size="lg" className="flex-1" onClick={onDone}>
          Skip it
        </Button>
        {canMakePlan && (
          <Button size="lg" className="flex-1" onClick={handleMakePlan} disabled={savingPlan}>
            Make a plan
          </Button>
        )}
      </div>
    </div>
  )
}
