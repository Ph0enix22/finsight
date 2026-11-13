import { Outlet } from 'react-router-dom'

import { BottomNav } from '@/components/BottomNav'
import { DarkModeToggle } from '@/components/DarkModeToggle'

export function Shell() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[430px] flex-col bg-background sm:border-x sm:border-border">
      <header className="flex items-center justify-between px-4 py-3">
        <span className="font-heading text-h2 font-semibold text-foreground">FinSight</span>
        <DarkModeToggle />
      </header>
      <main className="flex-1 overflow-y-auto px-4 pb-4">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
