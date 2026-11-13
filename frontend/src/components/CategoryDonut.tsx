import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

import { formatINR } from '@/lib/format'
import { CATEGORY_LABELS, type Category } from '@/lib/types'

// Fixed hue order (dataviz skill categorical palette, slots 1-6 + 8 in
// index.css) — picked to cover aarav's actual spend mix with its own color;
// anything else folds into one combined "Other" slice, never a generated hue.
const CATEGORY_SLOT: Partial<Record<Category, number>> = {
  food_delivery: 1,
  dining_cafe: 2,
  groceries_qcommerce: 3,
  transport: 4,
  subscriptions: 5,
  shopping: 6,
  transfers_friends: 7,
}

export interface CategoryTotal {
  category: Category
  totalPaise: number
}

interface Slice {
  key: string
  label: string
  totalPaise: number
  color: string
}

function buildSlices(data: CategoryTotal[]): Slice[] {
  const dedicated: Slice[] = []
  let otherTotal = 0

  for (const { category, totalPaise } of data) {
    const slot = CATEGORY_SLOT[category]
    if (slot) {
      dedicated.push({ key: category, label: CATEGORY_LABELS[category], totalPaise, color: `var(--cat-${slot})` })
    } else {
      otherTotal += totalPaise
    }
  }

  dedicated.sort((a, b) => b.totalPaise - a.totalPaise)
  if (otherTotal > 0) {
    dedicated.push({ key: 'other', label: 'Other', totalPaise: otherTotal, color: 'var(--cat-other)' })
  }
  return dedicated
}

export function CategoryDonut({ data }: { data: CategoryTotal[] }) {
  const slices = buildSlices(data)
  const total = slices.reduce((sum, s) => sum + s.totalPaise, 0)

  return (
    <div>
      <div className="relative mx-auto h-48 w-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="totalPaise"
              nameKey="label"
              innerRadius="70%"
              outerRadius="100%"
              stroke="var(--card)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {slices.map((slice) => (
                <Cell key={slice.key} fill={slice.color} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <p className="font-heading text-h2 font-semibold tabular-nums text-foreground">
            {formatINR(total)}
          </p>
          <p className="text-micro text-muted-foreground">total</p>
        </div>
      </div>

      <ul className="mt-4 space-y-2">
        {slices.map((slice) => (
          <li key={slice.key} className="flex items-center gap-2 text-small">
            <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: slice.color }} />
            <span className="flex-1 text-foreground">{slice.label}</span>
            <span className="text-muted-foreground">
              {total > 0 ? Math.round((slice.totalPaise / total) * 100) : 0}%
            </span>
            <span className="w-20 text-right tabular-nums text-foreground">{formatINR(slice.totalPaise)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
