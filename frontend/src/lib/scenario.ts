import { addDays } from '@/lib/date'
import type { Direction, RecurringSeries, ScenarioEvent } from '@/lib/types'

export type ScenarioKind = 'buy' | 'emi' | 'trip' | 'subscription' | 'goal'

export const SCENARIO_KIND_LABELS: Record<ScenarioKind, string> = {
  buy: 'Buy something',
  emi: 'Start an EMI',
  trip: 'Plan a trip',
  subscription: 'Subscription',
  goal: 'Savings goal',
}

export type BuyMode = 'now' | 'emi' | 'save_up'

export interface BuyScenarioState {
  kind: 'buy'
  amountPaise: number
  date: string
  mode: BuyMode
  emiMonths: number
  /** True when this "buy" is actually money NOT spent (e.g. "cut food orders
   * in half") — amountPaise stays a positive magnitude for editing, this flag
   * flips it to a balance-boosting negative amount at build time. Only
   * meaningful for mode 'now'. */
  isReduction?: boolean
}

export interface EmiScenarioState {
  kind: 'emi'
  amountPaise: number
  months: number
  startDate: string
}

export interface TripScenarioState {
  kind: 'trip'
  amountPaise: number
  startDate: string
  endDate: string
}

export interface SubscriptionScenarioState {
  kind: 'subscription'
  mode: 'cancel' | 'add'
  merchantId: number | null
  amountPaise: number
  periodDays: number
  nextDue: string
}

export interface GoalScenarioState {
  kind: 'goal'
  targetAmountPaise: number
  targetDate: string
}

export type ScenarioFormState =
  | BuyScenarioState
  | EmiScenarioState
  | TripScenarioState
  | SubscriptionScenarioState
  | GoalScenarioState

/** What a card/row/chat hand-off actually carries — kept separate from the full
 * form state so callers (Today's insight card, TxnRow, chat) don't need to know
 * about modes/months/etc., just "here's the purchase/cut to pre-load". */
export type ScenarioPrefill =
  | { type: 'one_time_purchase'; amountPaise: number; label?: string }
  | { type: 'recurring_cancel'; merchantId: number; typicalAmountPaise: number }

export function defaultScenarioState(kind: ScenarioKind, asOfDate: string): ScenarioFormState {
  switch (kind) {
    case 'buy':
      return { kind: 'buy', amountPaise: 500000, date: asOfDate, mode: 'now', emiMonths: 6 }
    case 'emi':
      return { kind: 'emi', amountPaise: 1500000, months: 12, startDate: asOfDate }
    case 'trip':
      return {
        kind: 'trip',
        amountPaise: 800000,
        startDate: addDays(asOfDate, 14),
        endDate: addDays(asOfDate, 19),
      }
    case 'subscription':
      return {
        kind: 'subscription',
        mode: 'cancel',
        merchantId: null,
        amountPaise: 20000,
        periodDays: 30,
        nextDue: addDays(asOfDate, 30),
      }
    case 'goal':
      return { kind: 'goal', targetAmountPaise: 5000000, targetDate: addDays(asOfDate, 180) }
  }
}

/** Maps a prefill handed off from elsewhere in the app into form state the
 * picker can render and a user can keep adjusting. */
export function scenarioStateFromPrefill(prefill: ScenarioPrefill, asOfDate: string): ScenarioFormState {
  if (prefill.type === 'recurring_cancel') {
    return {
      kind: 'subscription',
      mode: 'cancel',
      merchantId: prefill.merchantId,
      amountPaise: prefill.typicalAmountPaise,
      periodDays: 30,
      nextDue: asOfDate,
    }
  }
  return {
    kind: 'buy',
    amountPaise: Math.abs(prefill.amountPaise),
    date: asOfDate,
    mode: 'now',
    emiMonths: 6,
    isReduction: prefill.amountPaise < 0,
  }
}

const PROMPT_KEYWORDS: { pattern: RegExp; kind: ScenarioKind }[] = [
  { pattern: /emi/i, kind: 'emi' },
  { pattern: /trip|travel|vacation|goa/i, kind: 'trip' },
  { pattern: /cancel|skip a bill|subscription|sub\b/i, kind: 'subscription' },
  { pattern: /goal|save up|saving/i, kind: 'goal' },
]

export function scenarioKindFromPrompt(prompt: string): ScenarioKind {
  for (const { pattern, kind } of PROMPT_KEYWORDS) {
    if (pattern.test(prompt)) return kind
  }
  return 'buy'
}

export interface ScenarioBuild {
  events: ScenarioEvent[]
  goalTargetAmountPaise?: number
}

export function buildScenarioEvents(state: ScenarioFormState): ScenarioBuild {
  switch (state.kind) {
    case 'buy':
      if (state.mode === 'now') {
        const signedAmount = state.isReduction ? -state.amountPaise : state.amountPaise
        return { events: [{ type: 'one_time_purchase', amount_paise: signedAmount, date: state.date }] }
      }
      if (state.mode === 'emi') {
        return {
          events: [
            {
              type: 'emi',
              amount_paise: Math.round(state.amountPaise / state.emiMonths),
              months: state.emiMonths,
              start_date: state.date,
            },
          ],
        }
      }
      return {
        events: [{ type: 'goal', target_amount_paise: state.amountPaise, target_date: state.date }],
        goalTargetAmountPaise: state.amountPaise,
      }
    case 'emi':
      return {
        events: [
          { type: 'emi', amount_paise: state.amountPaise, months: state.months, start_date: state.startDate },
        ],
      }
    case 'trip':
      return {
        events: [
          {
            type: 'trip',
            amount_paise: state.amountPaise,
            start_date: state.startDate,
            end_date: state.endDate,
          },
        ],
      }
    case 'subscription':
      if (state.mode === 'cancel') {
        if (state.merchantId == null) return { events: [] }
        return { events: [{ type: 'recurring_change', mode: 'cancel', merchant_id: state.merchantId }] }
      }
      return {
        events: [
          {
            type: 'recurring_change',
            mode: 'add',
            direction: 'DR' as Direction,
            period_days: state.periodDays,
            typical_amount_paise: state.amountPaise,
            next_due: state.nextDue,
          },
        ],
      }
    case 'goal':
      return {
        events: [{ type: 'goal', target_amount_paise: state.targetAmountPaise, target_date: state.targetDate }],
        goalTargetAmountPaise: state.targetAmountPaise,
      }
  }
}

export function activeSubscriptions(series: RecurringSeries[]): RecurringSeries[] {
  return series.filter((s) => s.direction === 'DR')
}
