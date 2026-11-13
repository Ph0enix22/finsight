import { daysBetween } from '@/lib/date'
import type { Transaction } from '@/lib/types'

export function safeToSpendPerDayPaise(
  currentBalancePaise: number,
  asOfDate: string,
  nextInflowDate: string,
): number {
  const days = Math.max(daysBetween(asOfDate, nextInflowDate), 1)
  return Math.round(currentBalancePaise / days)
}

export interface BalancePoint {
  date: string
  balance: number
}

/** `transactionsDescByTs` must be sorted newest-first, as `GET /transactions` returns them. */
export function balanceHistory(transactionsDescByTs: Transaction[]): BalancePoint[] {
  return transactionsDescByTs
    .filter((t) => t.balance_after_paise != null)
    .map((t) => ({ date: t.ts, balance: t.balance_after_paise as number }))
    .reverse()
}
