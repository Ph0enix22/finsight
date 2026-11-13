import { ArrowRight } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'

const QUICK_CHIPS = ['Buy something', 'Skip a bill', 'New EMI', 'Cancel a sub']

export function WhatIfBar() {
  const navigate = useNavigate()
  const [value, setValue] = useState('')

  const go = (prompt?: string) => navigate('/whatif', { state: { prompt: prompt ?? value } })

  return (
    <div className="sticky bottom-0 -mx-4 mt-4 border-t border-border bg-background px-4 pt-3 pb-1">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          go()
        }}
        className="flex items-center gap-2"
      >
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="What if I..."
          aria-label="What if I..."
          className="min-h-11 flex-1 rounded-input border border-border bg-card px-4 text-body text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        />
        <Button type="submit" size="icon" aria-label="Simulate">
          <ArrowRight size={18} />
        </Button>
      </form>
      <div className="mt-2 flex gap-2 overflow-x-auto pb-2">
        {QUICK_CHIPS.map((chip) => (
          <button
            key={chip}
            type="button"
            onClick={() => go(chip)}
            className="shrink-0 whitespace-nowrap rounded-full border border-border px-3 py-1.5 text-micro text-muted-foreground hover:border-scenario hover:text-scenario"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  )
}
