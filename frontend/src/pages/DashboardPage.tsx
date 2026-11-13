import { useQuery } from '@tanstack/react-query'
import {
  Activity as ActivityIcon, AlertOctagon, AlertTriangle, Bike, CheckCircle2, Clock, Info, PackageCheck, PackageX, ShieldAlert, Truck,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { usePeriod } from '@/hooks/usePeriod'
import { get } from '@/lib/api'
import { fmtMin, INCIDENT_TYPE_LABEL, label, STATUS_LABEL, timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Alert, Charts, Overview } from '@/types/api'

const COLORS = ['#6366F1', '#22D3EE', '#22C55E', '#F59E0B', '#EF4444', '#A78BFA', '#38BDF8', '#94A3B8']
const AXIS = { fontSize: 11, fill: '#9CA3AF' }
const tooltipStyle = { background: '#111827', border: '1px solid #273244', borderRadius: 8, fontSize: 12 }

function bucketLabel(iso: string, granularity: Charts['granularity']) {
  const d = new Date(iso)
  return granularity === 'day' ? d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function Kpi({ title, value, hint, icon, tone = 'text-fg', to }: { title: string; value: ReactNode; hint?: string; icon: ReactNode; tone?: string; to?: string }) {
  const body = (
    <Card className={cn('h-full transition-colors', to && 'hover:border-primary/50')}>
      <CardContent className="flex items-start justify-between gap-3 pt-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">{title}</p>
          <p className={cn('tabular mt-1 text-2xl font-semibold tracking-tight', tone)}>{value}</p>
          {hint && <p className="mt-0.5 truncate text-[11px] text-muted">{hint}</p>}
        </div>
        <div className="rounded-lg bg-surface-2 p-2 text-muted">{icon}</div>
      </CardContent>
    </Card>
  )
  return to ? <Link to={to} className="block">{body}</Link> : body
}

const ALERT_STYLE = {
  CRITICAL: { tone: 'danger' as const, icon: AlertOctagon, text: 'Crítico', ring: 'border-danger/40 bg-danger/5' },
  WARNING: { tone: 'warn' as const, icon: AlertTriangle, text: 'Atenção', ring: 'border-warn/40 bg-warn/5' },
  INFO: { tone: 'accent' as const, icon: Info, text: 'Informativo', ring: 'border-accent/30 bg-accent/5' },
}

function AlertList({ alerts }: { alerts: Alert[] }) {
  return (
    <ul className="space-y-2">
      {alerts.map((a) => {
        const s = ALERT_STYLE[a.level]
        return (
          <li key={a.id} className={cn('rounded-lg border p-3', s.ring)}>
            <div className="flex items-center gap-2">
              <s.icon className="h-4 w-4 shrink-0" aria-hidden />
              <span className="text-sm font-medium">{a.title}</span>
              <Badge tone={s.tone} className="ml-auto">{s.text}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted">{a.message}</p>
            {a.orders.length > 0 && (
              <p className="mt-1.5 flex flex-wrap gap-1">
                {a.orders.slice(0, 6).map((c) => (
                  <Link key={c} to={`/pedidos?q=${c.replace('ORD-', '')}`} className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-accent hover:underline">{c}</Link>
                ))}
                {a.orders.length > 6 && <span className="text-[10px] text-muted">+{a.orders.length - 6}</span>}
              </p>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ChartCard({ title, description, children, empty }: { title: string; description?: string; children: ReactNode; empty?: boolean }) {
  return (
    <Card>
      <CardHeader><div><CardTitle>{title}</CardTitle>{description && <CardDescription>{description}</CardDescription>}</div></CardHeader>
      <CardContent className="h-64">{empty ? <EmptyState title="Sem dados no período" hint="Altere o período ou avance a simulação." /> : children}</CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { hours, label: periodLabel } = usePeriod()
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['overview', hours], queryFn: () => get<Overview>('/dashboard/overview', { hours }), refetchInterval: 30_000,
  })

  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (isLoading || !data) {
    return <div className="space-y-4"><Skeleton className="h-8 w-56" /><div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div><Skeleton className="h-64" /></div>
  }
  const { kpis: k, charts: c, alerts, activity } = data
  const g = c.granularity

  return (
    <>
      <PageHeader title="Dashboard operacional" description={`${periodLabel} · indicadores calculados a partir do banco de dados (dados simulados)`} />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Kpi title="Total de pedidos" value={k.total_orders} hint="criados no período" icon={<PackageCheck className="h-4 w-4" />} to="/pedidos" />
        <Kpi title="Em andamento" value={k.in_progress} hint={`${k.waiting_courier} aguardando entregador`} icon={<Truck className="h-4 w-4" />} to="/pedidos" />
        <Kpi title="Entregues" value={k.delivered} icon={<CheckCircle2 className="h-4 w-4" />} tone="text-success" to="/pedidos?status=DELIVERED" />
        <Kpi title="Atrasados" value={k.delayed} hint={`${k.at_risk} em risco de atraso`} icon={<AlertTriangle className="h-4 w-4" />} tone={k.delayed ? 'text-danger' : 'text-fg'} to="/pedidos?situation=delayed" />
        <Kpi title="Cancelados" value={k.cancelled} icon={<PackageX className="h-4 w-4" />} tone={k.cancelled ? 'text-warn' : 'text-fg'} to="/pedidos?status=CANCELLED" />
        <Kpi title="Tempo médio de entrega" value={fmtMin(k.avg_delivery_minutes)} hint="pedidos entregues" icon={<Clock className="h-4 w-4" />} />
        <Kpi title="Entregadores disponíveis" value={`${k.available_couriers}/${k.total_couriers}`} icon={<Bike className="h-4 w-4" />} tone={k.available_couriers === 0 ? 'text-danger' : 'text-accent'} to="/entregadores" />
        <Kpi title="Ocorrências abertas" value={k.open_incidents} icon={<ShieldAlert className="h-4 w-4" />} tone={k.open_incidents ? 'text-warn' : 'text-fg'} to="/ocorrencias" />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <ChartCard title="Volume de pedidos" description={g === 'hour' ? 'Pedidos criados por hora' : 'Pedidos criados por dia'} empty={c.order_volume.every((p) => p.orders === 0)}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={c.order_volume.map((p) => ({ ...p, label: bucketLabel(p.bucket, g) }))} margin={{ left: -20, right: 8, top: 8 }}>
                <defs><linearGradient id="vol" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6366F1" stopOpacity={0.5} /><stop offset="100%" stopColor="#6366F1" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid stroke="#273244" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: '#9CA3AF' }} formatter={(v) => [v, 'Pedidos']} />
                <Area type="monotone" dataKey="orders" stroke="#6366F1" strokeWidth={2} fill="url(#vol)" />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
          <div className="grid gap-4 md:grid-cols-2">
            <ChartCard title="Tempo médio de entrega" description="Minutos, por período de criação" empty={c.avg_delivery_time.every((p) => p.minutes == null)}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={c.avg_delivery_time.map((p) => ({ ...p, label: bucketLabel(p.bucket, g) }))} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid stroke="#273244" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v} min`, 'Tempo médio']} />
                  <Line type="monotone" dataKey="minutes" stroke="#22D3EE" strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Evolução de cancelamentos" empty={c.cancellations.every((p) => p.cancelled === 0)}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={c.cancellations.map((p) => ({ ...p, label: bucketLabel(p.bucket, g) }))} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid stroke="#273244" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => [v, 'Cancelados']} cursor={{ fill: '#1F2937' }} />
                  <Bar dataKey="cancelled" fill="#EF4444" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader><div><CardTitle>Alertas inteligentes</CardTitle><CardDescription>Calculados por regras de negócio verificáveis</CardDescription></div></CardHeader>
            <CardContent><AlertList alerts={alerts} /></CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Pedidos por status" empty={c.orders_by_status.length === 0}>
          <div className="flex h-full flex-col gap-2">
            <div className="min-h-0 flex-1">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={c.orders_by_status.map((s) => ({ name: label(STATUS_LABEL, s.status), value: s.count }))} dataKey="value" nameKey="name" innerRadius="55%" outerRadius="90%" paddingAngle={2} stroke="none">
                    {c.orders_by_status.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
              {c.orders_by_status.map((s, i) => (
                <li key={s.status} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} aria-hidden />{label(STATUS_LABEL, s.status)} <b className="tabular text-fg">{s.count}</b></li>
              ))}
            </ul>
          </div>
        </ChartCard>
        <ChartCard title="Distribuição de ocorrências" description="Criadas no período" empty={c.incident_distribution.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart layout="vertical" data={c.incident_distribution.map((d) => ({ name: label(INCIDENT_TYPE_LABEL, d.type), count: d.count }))} margin={{ left: 0, right: 8 }}>
              <CartesianGrid stroke="#273244" strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={AXIS} tickLine={false} axisLine={false} width={130} interval={0} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#1F2937' }} formatter={(v) => [v, 'Ocorrências']} />
              <Bar dataKey="count" fill="#F59E0B" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Desempenho por restaurante" description="Pedidos e preparo médio (min)" empty={c.restaurant_performance.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart layout="vertical" data={c.restaurant_performance.slice(0, 6)} margin={{ left: 0, right: 8 }}>
              <CartesianGrid stroke="#273244" strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={AXIS} tickLine={false} axisLine={false} width={120} interval={0} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#1F2937' }} formatter={(v, n) => [n === 'orders' ? v : `${v} min`, n === 'orders' ? 'Pedidos' : 'Preparo médio']} />
              <Legend iconType="circle" iconSize={8} formatter={(v) => <span className="text-[11px] text-muted">{v === 'orders' ? 'Pedidos' : 'Preparo médio (min)'}</span>} />
              <Bar dataKey="orders" fill="#6366F1" radius={[0, 3, 3, 0]} barSize={8} />
              <Bar dataKey="avg_prep_minutes" fill="#22D3EE" radius={[0, 3, 3, 0]} barSize={8} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <div><CardTitle className="flex items-center gap-2"><ActivityIcon className="h-4 w-4 text-accent" />Atividade recente</CardTitle><CardDescription>Eventos reais registrados pelo sistema</CardDescription></div>
          <Link to="/atividades" className="text-xs text-accent hover:underline">Ver histórico completo</Link>
        </CardHeader>
        <CardContent>
          {activity.length === 0 ? <EmptyState title="Nenhuma atividade registrada" /> : (
            <ul className="divide-y divide-line">
              {activity.map((a) => (
                <li key={a.id} className="flex items-center gap-3 py-2.5 text-sm">
                  <span className={cn('h-2 w-2 shrink-0 rounded-full', a.severity === 'CRITICAL' ? 'bg-danger' : a.severity === 'WARNING' ? 'bg-warn' : 'bg-accent')} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{a.message}</span>
                  <span className="shrink-0 text-xs text-muted">{timeAgo(a.created_at, new Date(data.generated_at).getTime())}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </>
  )
}
