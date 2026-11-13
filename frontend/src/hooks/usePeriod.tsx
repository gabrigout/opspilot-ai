import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export const PERIODS = [
  { hours: 6, label: 'Últimas 6 h' },
  { hours: 24, label: 'Últimas 24 h' },
  { hours: 72, label: 'Últimos 3 dias' },
  { hours: 168, label: 'Últimos 7 dias' },
]

interface PeriodState { hours: number; setHours: (h: number) => void; label: string }
const Ctx = createContext<PeriodState | null>(null)
const KEY = 'opspilot_period'

function initial(): number {
  try {
    const v = Number(localStorage.getItem(KEY))
    if (PERIODS.some((p) => p.hours === v)) return v
  } catch { /* storage unavailable */ }
  return 24
}

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [hours, set] = useState(initial)
  const value = useMemo<PeriodState>(() => ({
    hours,
    label: PERIODS.find((p) => p.hours === hours)?.label ?? `${hours} h`,
    setHours: (h) => {
      set(h)
      try { localStorage.setItem(KEY, String(h)) } catch { /* ignore */ }
    },
  }), [hours])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function usePeriod() {
  const c = useContext(Ctx)
  if (!c) throw new Error('usePeriod must be used inside <PeriodProvider>')
  return c
}
