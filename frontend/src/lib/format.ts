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

export function formatINR(paise: number): string {
  return inrFormatter.format(paise / 100)
}

export function formatDate(iso: string | Date): string {
  const date = typeof iso === 'string' ? new Date(iso) : iso
  return dateFormatter.format(date)
}
