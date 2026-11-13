const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

const dateFormatter = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  timeZone: 'Asia/Kolkata',
})

const dateWithWeekdayFormatter = new Intl.DateTimeFormat('en-IN', {
  weekday: 'short',
  day: '2-digit',
  month: 'short',
  timeZone: 'Asia/Kolkata',
})

const timeFormatter = new Intl.DateTimeFormat('en-IN', {
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
  timeZone: 'Asia/Kolkata',
})

export function formatINR(paise: number): string {
  return inrFormatter.format(paise / 100)
}

/** Short axis-label form: ₹3k, ₹1.2L, ₹0 — never the full grouped figure. */
export function formatINRShort(paise: number): string {
  const rupees = Math.round(paise / 100)
  if (rupees >= 100_000) {
    const lakh = rupees / 100_000
    return `₹${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(1)}L`
  }
  if (rupees >= 1_000) {
    return `₹${Math.round(rupees / 1_000)}k`
  }
  return `₹${rupees}`
}

export function formatDate(iso: string | Date): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso
  return dateFormatter.format(date)
}

/** "Sat, 14 Nov" */
export function formatDateWithWeekday(iso: string | Date): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso
  return dateWithWeekdayFormatter.format(date)
}

export function formatTime(iso: string | Date): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso
  return timeFormatter.format(date)
}

export function merchantInitial(name: string | null): string {
  return (name ?? '?').trim().charAt(0).toUpperCase() || '?'
}
