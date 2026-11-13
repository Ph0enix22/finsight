import { Activity, Compass, Home, MessageCircle, Radar } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/today', label: 'Today', icon: Home, raised: false },
  { to: '/activity', label: 'Activity', icon: Activity, raised: false },
  { to: '/whatif', label: 'What-if', icon: Compass, raised: true },
  { to: '/ask', label: 'Ask', icon: MessageCircle, raised: false },
  { to: '/radar', label: 'Radar', icon: Radar, raised: false },
] as const

export function BottomNav() {
  return (
    <nav className="flex items-center justify-between border-t border-border bg-card px-2 pb-[max(env(safe-area-inset-bottom),8px)] pt-2">
      {navItems.map(({ to, label, icon: Icon, raised }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex min-h-11 min-w-11 flex-1 flex-col items-center justify-center gap-1 rounded-card py-1 text-micro ${
              raised ? '-mt-6 rounded-full bg-primary text-primary-foreground shadow-md' : ''
            } ${isActive && !raised ? 'text-primary' : raised ? '' : 'text-muted-foreground'}`
          }
        >
          <Icon size={raised ? 22 : 20} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
