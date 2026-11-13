import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

function getInitialTheme(): boolean {
  const stored = localStorage.getItem('theme')
  if (stored) return stored === 'dark'
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function DarkModeToggle() {
  const [isDark, setIsDark] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
    localStorage.setItem('theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return (
    <button
      type="button"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => setIsDark((value) => !value)}
      className="flex size-11 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
    >
      {isDark ? <Sun size={20} /> : <Moon size={20} />}
    </button>
  )
}
