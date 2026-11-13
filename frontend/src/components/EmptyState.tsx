import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'

interface EmptyStateProps {
  icon: LucideIcon
  heading: string
  subcopy: string
  action?: { label: string; onClick: () => void }
}

export function EmptyState({ icon: Icon, heading, subcopy, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <Icon className="text-muted-foreground" size={28} strokeWidth={1.5} />
      <p className="font-heading text-h2 text-foreground">{heading}</p>
      <p className="max-w-[260px] text-small text-muted-foreground">{subcopy}</p>
      {action && (
        <Button variant="outline" size="sm" onClick={action.onClick} className="mt-2">
          {action.label}
        </Button>
      )}
    </div>
  )
}

export function ErrorState({
  heading = 'Something went sideways',
  subcopy = 'That request did not come through. Try again.',
  onRetry,
}: {
  heading?: string
  subcopy?: string
  onRetry: () => void
}): ReactNode {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="font-heading text-h2 text-foreground">{heading}</p>
      <p className="max-w-[260px] text-small text-muted-foreground">{subcopy}</p>
      <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
        Retry
      </Button>
    </div>
  )
}
