import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, get, post, tokenStore } from '@/lib/api'
import type { Token, User } from '@/types/api'

interface AuthState {
  user: User | null
  loading: boolean
  canWrite: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState<boolean>(() => !!tokenStore.get())

  useEffect(() => {
    if (!tokenStore.get()) return
    let cancelled = false
    // Only an explicit 401 ends the session: transient network/5xx errors must not log the user out.
    const restore = async (attempt: number): Promise<void> => {
      try {
        const me = await get<User>('/auth/me')
        if (!cancelled) setUser(me)
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) tokenStore.clear()
        else if (attempt < 3) {
          await new Promise((r) => setTimeout(r, 600 * attempt))
          if (!cancelled) return restore(attempt + 1)
        }
      }
    }
    void restore(1).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const onUnauthorized = () => { setUser(null); qc.clear() }
    window.addEventListener('opspilot:unauthorized', onUnauthorized)
    return () => window.removeEventListener('opspilot:unauthorized', onUnauthorized)
  }, [qc])

  const login = useCallback(async (email: string, password: string) => {
    const t = await post<Token>('/auth/login', { email, password })
    tokenStore.set(t.access_token)
    setUser(t.user)
  }, [])

  const logout = useCallback(async () => {
    try { await post('/auth/logout') } catch { /* token may already be invalid */ }
    tokenStore.clear()
    setUser(null)
    qc.clear()
  }, [qc])

  const value = useMemo<AuthState>(
    () => ({ user, loading, canWrite: user?.role === 'ADMIN' || user?.role === 'OPERATOR', login, logout }),
    [user, loading, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
