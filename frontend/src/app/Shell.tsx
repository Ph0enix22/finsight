import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { BottomNav } from '@/components/BottomNav'
import { DarkModeToggle } from '@/components/DarkModeToggle'
import { DesktopWordmark } from '@/components/DesktopWordmark'
import { useSession } from '@/lib/session'

const PERSONA_LABELS: Record<string, string> = {
  aarav: 'aarav · hostel B.Tech',
  priya: 'priya · SDE, Bengaluru',
  fatima: 'fatima · design student',
  custom: 'your data',
}

export function Shell() {
  const { session } = useSession()
  const location = useLocation()

  if (!session) return <Navigate to="/" replace />

  // Today has its own "Hi <name>" greeting as the page's hero line — the
  // generic FinSight wordmark would just repeat that, so it's Today-only.
  const showWordmark = location.pathname !== '/today'

  return (
    <>
      <DesktopWordmark personaName={PERSONA_LABELS[session.personaKey] ?? session.personaKey} />
      <div className="mx-auto min-h-screen w-full max-w-[430px] bg-background sm:border-x sm:border-border lg:my-6 lg:rounded-[2rem] lg:border lg:border-border lg:shadow-2xl">
        <header className="flex items-center justify-between px-4 py-3">
          {showWordmark ? (
            <span className="font-heading text-h2 font-semibold text-foreground">FinSight</span>
          ) : (
            <span />
          )}
          <DarkModeToggle />
        </header>
        <main className="px-4 pb-[calc(var(--nav-h)+env(safe-area-inset-bottom)+16px)]">
          <Outlet />
        </main>
      </div>
      <BottomNav />
    </>
  )
}
