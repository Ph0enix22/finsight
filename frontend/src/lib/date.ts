const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000

/**
 * The IST (Asia/Kolkata) calendar-day a stored UTC instant falls on — e.g.
 * "2026-11-14T22:14:00Z" is 14-Nov in UTC but genuinely IST-local, so the
 * correct calendar day is derived by shifting +5:30 before reading the date.
 * Never slice a full timestamp's date portion directly (that reads the UTC
 * day, which can differ from the IST day the user actually sees).
 */
export function toISTDateString(isoTimestamp: string): string {
  return new Date(new Date(isoTimestamp).getTime() + IST_OFFSET_MS).toISOString().slice(0, 10)
}

export function addDays(iso: string, days: number): string {
  const d = new Date(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function daysBetween(fromIso: string, toIso: string): number {
  const from = new Date(fromIso.slice(0, 10))
  const to = new Date(toIso.slice(0, 10))
  return Math.round((to.getTime() - from.getTime()) / 86_400_000)
}

export function firstOfNextMonth(iso: string): string {
  const d = new Date(iso.slice(0, 10))
  const next = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))
  return next.toISOString().slice(0, 10)
}

export function firstOfMonth(iso: string): string {
  const d = new Date(iso.slice(0, 10))
  const start = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1))
  return start.toISOString().slice(0, 10)
}
