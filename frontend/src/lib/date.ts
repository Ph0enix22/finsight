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
