import { CATEGORY_LABELS, type Category } from '@/lib/types'

interface FilterChipsProps {
  categories: Category[]
  active: Category | null
  onChange: (category: Category | null) => void
}

export function FilterChips({ categories, active, onChange }: FilterChipsProps) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Filter by category">
      <Chip label="All" selected={active === null} onClick={() => onChange(null)} />
      {categories.map((category) => (
        <Chip
          key={category}
          label={CATEGORY_LABELS[category]}
          selected={active === category}
          onClick={() => onChange(active === category ? null : category)}
        />
      ))}
    </div>
  )
}

function Chip({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`min-h-8 shrink-0 whitespace-nowrap rounded-full px-3 text-micro font-medium transition-colors ${
        selected
          ? 'bg-primary text-primary-foreground'
          : 'border border-border text-muted-foreground hover:text-foreground'
      }`}
    >
      {label}
    </button>
  )
}
