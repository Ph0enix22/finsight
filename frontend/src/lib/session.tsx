import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

export interface Session {
  userId: number
  accountId: number
  personaKey: string
}

const STORAGE_KEY = 'finsight.session'

function readStoredSession(): Session | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Session
  } catch {
    return null
  }
}

interface SessionContextValue {
  session: Session | null
  setSession: (session: Session) => void
  clearSession: () => void
}

const SessionContext = createContext<SessionContextValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(readStoredSession)

  const setSession = useCallback((next: Session) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setSessionState(next)
  }, [])

  const clearSession = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setSessionState(null)
  }, [])

  const value = useMemo(() => ({ session, setSession, clearSession }), [session, setSession, clearSession])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}
