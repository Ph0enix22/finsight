import { FOOD_SPEND_CATEGORIES, MICRO_FOOD_SPEND_CEILING_PAISE } from '@/lib/foodSpend'
import type { Transaction } from '@/lib/types'

export interface FoodSpendInsight {
  count: number
  totalPaise: number
  txnIds: number[]
}

/** Real arithmetic over real transactions — a filter + sum, not a model. */
export function computeFoodUnderThresholdInsight(transactions: Transaction[]): FoodSpendInsight {
  const matches = transactions.filter(
    (t) =>
      t.direction === 'DR' &&
      t.category != null &&
      (FOOD_SPEND_CATEGORIES as string[]).includes(t.category) &&
      t.amount_paise < MICRO_FOOD_SPEND_CEILING_PAISE,
  )
  return {
    count: matches.length,
    totalPaise: matches.reduce((sum, t) => sum + t.amount_paise, 0),
    txnIds: matches.map((t) => t.id),
  }
}

// TODO(phase6): replace with GET /radar — the real IsolationForest + novelty
// scoring lands there. Until then, resolve the one known scripted-demo
// anomaly by its structured identity (merchant + amount), never by scanning
// raw_text, so it still shows up with a real txn id/receipt.
const KNOWN_ANOMALY_FIXTURES: Record<string, { merchantName: string; amountPaise: number }> = {
  aarav: { merchantName: 'QuickFix Mobile Repair Kiosk', amountPaise: 249_900 },
}

export function findKnownAnomaly(transactions: Transaction[], personaKey: string): Transaction | null {
  const fixture = KNOWN_ANOMALY_FIXTURES[personaKey]
  if (!fixture) return null
  return (
    transactions.find(
      (t) => t.merchant_name === fixture.merchantName && t.amount_paise === fixture.amountPaise,
    ) ?? null
  )
}
