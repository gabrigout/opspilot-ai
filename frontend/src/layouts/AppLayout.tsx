import { useQuery } from '@tanstack/react-query'
import {
  Bell, Bot, ClipboardList, FileBarChart, History, LayoutDashboard, LogOut, Menu, PanelLeftClose, PanelLeftOpen,
  Settings, ShieldAlert, Store, Bike, Clock, X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/field'
import { useAuth } from '@/hooks/useAuth'
import { PERIODS, usePeriod } from '@/hooks/usePeriod'
import { fmtDateTime } from '@/lib/format'
import { get } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { AiStatus, Alert, SimStatus } from '@/types/api'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/pedidos', label: 'Pedidos', icon: ClipboardList },
  { to: '/entregadores', label: 'Entregadores', icon: Bike },
  { to: '/restaurantes', label: 'Restaurantes', icon: Store },
  { to: '/ocorrencias', label: 'Ocorrências', icon: ShieldAlert },
  { to: '/copilot', label: 'AI Copilot', icon: Bot },
  { to: '/relatorios', label: 'Relatórios', icon: FileBarChart },
  { to: '/atividades', label: 'Atividades', icon: History },
  { to: '/configuracoes', label: 'Configurações', icon: Settings },
]

function Logo({ collapsed }: { collapsed: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-1" aria-label="OpsPilot AI – início">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary shadow-lg shadow-primary/30">
        <svg viewBox="0 0 32 32" className="h-5 w-5" aria-hidden><path d="M8 20 L16 7 L24 20 L16 16.5 Z" fill="#F9FAFB" /><circle cx="16" cy="24" r="2" fill="#22D3EE" /></svg>
      </span>
      {!collapsed && <span className="text-[15px] font-semibold tracking-tight">OpsPilot <span className="text-accent">AI</span></span>}
    </Link>
  )
}

function AiIndicator() {
  const { data } = useQuery({ queryKey: ['ai-status'], queryFn: () => get<AiStatus>('/ai/status'), staleTime: 60_000 })
  if (!data) return null
  const demo = data.mode === 'demo'
  return (
    <Link to="/copilot" title={data.label} className="hidden items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs hover:bg-surface-2 sm:flex">
      <span className={cn('h-2 w-2 rounded-full', demo ? 'bg-warn' : 'bg-success')} aria-hidden />
      <span className="text-muted">IA:</span>
      <span className="font-medium">{demo ? 'Modo demonstrativo' : `${data.provider} · ${data.model}`}</span>
    </Link>
  )
}

function Notifications() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { data } = useQuery({ queryKey: ['alerts'], queryFn: () => get<{ items: Alert[] }>('/dashboard/alerts'), refetchInterval: 30_000 })
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const actionable = (data?.items ?? []).filter((a) => a.level !== 'INFO')
  const critical = actionable.some((a) => a.level === 'CRITICAL')
  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="icon" aria-label={`Notificações (${actionable.length})`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Bell className="h-[18px] w-[18px]" />
        {actionable.length > 0 && (
          <span className={cn('absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-semibold text-white', critical ? 'bg-danger' : 'bg-warn')}>
            {actionable.length}
          </span>
        )}
      </Button>
      {open && (
        <div role="dialog" aria-label="Notificações" className="absolute right-0 z-40 mt-2 w-[min(24rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-2 shadow-2xl shadow-black/50">
          <p className="px-2 py-1.5 text-xs font-semibold text-muted">Alertas operacionais</p>
          {actionable.length === 0 && <p className="px-2 py-4 text-center text-sm text-muted">Nenhum alerta ativo.</p>}
          <ul className="max-h-96 space-y-1 overflow-y-auto">
            {actionable.map((a) => (
              <li key={a.id} className="rounded-lg px-2 py-2 hover:bg-surface-2">
                <div className="flex items-center gap-2">
                  <Badge tone={a.level === 'CRITICAL' ? 'danger' : 'warn'}>{a.level === 'CRITICAL' ? 'Crítico' : 'Atenção'}</Badge>
                  <span className="text-sm font-medium">{a.title}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{a.message}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function SimClock() {
  const { data } = useQuery({ queryKey: ['sim-status'], queryFn: () => get<SimStatus>('/simulation/status'), refetchInterval: 20_000 })
  if (!data) return null
  return (
    <Link to="/configuracoes" className="hidden items-center gap-1.5 rounded-full border border-warn/30 bg-warn/10 px-3 py-1.5 text-xs text-warn lg:flex" title={data.notice}>
      <Clock className="h-3.5 w-3.5" aria-hidden /> Simulado · {fmtDateTime(data.now)}
    </Link>
  )
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const { hours, setHours } = usePeriod()
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('opspilot_sidebar') === '1' } catch { return false } })
  const [mobileOpen, setMobileOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => setMobileOpen(false), [loc.pathname])
  const toggle = () => setCollapsed((c) => { try { localStorage.setItem('opspilot_sidebar', c ? '0' : '1') } catch { /* ignore */ } return !c })

  const nav = (
    <nav aria-label="Principal" className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to} to={to} end={end} title={collapsed ? label : undefined}
          className={({ isActive }) => cn(
            'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
            isActive ? 'bg-primary/15 text-fg ring-1 ring-primary/30' : 'text-muted hover:bg-surface-2 hover:text-fg',
            collapsed && 'justify-center px-2',
          )}
        >
          <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
          <span className={cn(collapsed && 'sr-only')}>{label}</span>
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="flex h-full">
      <aside className={cn('hidden shrink-0 flex-col border-r border-line bg-surface/80 backdrop-blur transition-[width] duration-200 md:flex', collapsed ? 'w-[68px]' : 'w-60')}>
        <div className={cn('flex h-14 items-center border-b border-line px-4', collapsed && 'justify-center px-2')}><Logo collapsed={collapsed} /></div>
        {nav}
        <div className="border-t border-line p-3">
          <Button variant="ghost" size="sm" className={cn('w-full', collapsed ? 'px-0' : 'justify-start')} onClick={toggle} aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}>
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" />Recolher</>}
          </Button>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col border-r border-line bg-surface">
            <div className="flex h-14 items-center justify-between border-b border-line px-4">
              <Logo collapsed={false} />
              <Button variant="ghost" size="icon" aria-label="Fechar menu" onClick={() => setMobileOpen(false)}><X className="h-4 w-4" /></Button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-surface/70 px-3 backdrop-blur sm:gap-3 sm:px-5">
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Abrir menu" onClick={() => setMobileOpen(true)}><Menu className="h-5 w-5" /></Button>
          <div className="flex-1" />
          <SimClock />
          <AiIndicator />
          <label className="sr-only" htmlFor="period">Período</label>
          <Select id="period" value={hours} onChange={(e) => setHours(Number(e.target.value))} className="w-36">
            {PERIODS.map((p) => <option key={p.hours} value={p.hours}>{p.label}</option>)}
          </Select>
          <Notifications />
          <div className="flex items-center gap-2 border-l border-line pl-3">
            <div className="hidden text-right leading-tight sm:block">
              <p className="text-sm font-medium">{user?.full_name}</p>
              <p className="text-[11px] text-muted">{user?.role === 'ADMIN' ? 'Administrador' : user?.role === 'OPERATOR' ? 'Operador' : 'Visualizador'}</p>
            </div>
            <Button variant="ghost" size="icon" aria-label="Sair" title="Sair" onClick={() => void logout()}><LogOut className="h-[18px] w-[18px]" /></Button>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="mx-auto max-w-[1400px]"><Outlet /></div>
        </main>
      </div>
    </div>
  )
}
