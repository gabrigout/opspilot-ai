import { useQuery } from '@tanstack/react-query'
import { Clock, FastForward, Flame, PackagePlus, RotateCcw, UserMinus, UserPlus, Timer, XCircle, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { ErrorState, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select } from '@/components/ui/field'
import { useAuth } from '@/hooks/useAuth'
import { useAction } from '@/hooks/useMutationToast'
import { get, post } from '@/lib/api'
import { fmtDateTime } from '@/lib/format'
import type { AiStatus, Restaurant, SimStatus } from '@/types/api'

const RULE_LABEL: Record<string, string> = {
  delay_medium_minutes: 'Atraso → prioridade MÉDIA (min)', delay_high_minutes: 'Atraso → prioridade ALTA (min)', delay_critical_minutes: 'Atraso → prioridade CRÍTICA (min)',
  risk_remaining_minutes: 'Risco: restam ≤ N min e ainda não saiu para entrega', risk_in_delivery_remaining_minutes: 'Risco: em entrega com ≤ N min restantes',
  risk_no_courier_remaining_minutes: 'Risco: sem entregador e restam ≤ N min', courier_wait_minutes: 'Risco: aguardando entregador há ≥ N min',
  prep_overrun_minutes: 'Risco: preparo excedeu a estimativa em > N min', restaurant_prep_factor: 'Alerta de restaurante: preparo ≥ fator × média',
  restaurant_min_orders: 'Mínimo de pedidos para avaliar restaurante', critical_incident_open_minutes: 'Ocorrência crítica aberta há ≥ N min (alerta)',
  delayed_orders_critical_count: 'Pedidos atrasados para alerta crítico', max_courier_distance_km: 'Distância máxima de entregador elegível (km)',
}

function SimPanel() {
  const { canWrite, user } = useAuth()
  const [minutes, setMinutes] = useState('15')
  const [rest, setRest] = useState('')
  const [factor, setFactor] = useState('2')
  const [confirmReset, setConfirmReset] = useState(false)
  const status = useQuery({ queryKey: ['sim-status'], queryFn: () => get<SimStatus>('/simulation/status'), refetchInterval: 15_000 })
  const restaurants = useQuery({ queryKey: ['restaurants-lite'], queryFn: () => get<{ items: Restaurant[] }>('/restaurants', { period_hours: 24 }), staleTime: 300_000 })
  const advance = useAction((m: number) => post<Record<string, number | string>>('/simulation/advance', { minutes: m, auto_assign: true }),
    { success: (d) => `Relógio avançado: ${d.status_changes} mudanças de status, ${d.assignments} atribuições, ${d.newly_delayed} novos atrasos` })
  const act = useAction((b: Record<string, unknown>) => post<Record<string, unknown>>('/simulation/actions', b), { success: 'Cenário atualizado' })
  const reset = useAction(() => post('/simulation/reset'), { success: 'Ambiente de demonstração restaurado', onSuccess: () => setConfirmReset(false) })
  const disabled = !canWrite

  const Action = ({ icon, title, hint, onClick, busy }: { icon: React.ReactNode; title: string; hint: string; onClick: () => void; busy?: boolean }) => (
    <button disabled={disabled || act.isPending} onClick={onClick} aria-busy={busy}
      className="flex cursor-pointer items-start gap-3 rounded-lg border border-line bg-bg/40 p-3 text-left transition-colors hover:border-primary/60 hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50">
      <span className="mt-0.5 text-accent">{icon}</span><span><span className="block text-sm font-medium">{title}</span><span className="text-xs text-muted">{hint}</span></span>
    </button>
  )

  return (
    <Card>
      <CardHeader><div><CardTitle className="flex items-center gap-2"><Timer className="h-4 w-4 text-warn" />Simulador operacional</CardTitle>
        <CardDescription>Os efeitos gravam no banco: dashboard, relatórios e o AI Copilot passam a refletir o novo cenário. Todos os dados são fictícios.</CardDescription></div>
        <Badge tone="warn">Dados simulados</Badge></CardHeader>
      <CardContent className="space-y-5">
        {status.data && (
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-muted">Relógio simulado</dt><dd className="font-medium">{fmtDateTime(status.data.now)}</dd></div>
            <div><dt className="text-xs text-muted">Deslocamento</dt><dd className="tabular font-medium">+{Math.round(status.data.offset_minutes)} min</dd></div>
            <div><dt className="text-xs text-muted">Pedidos ativos</dt><dd className="tabular font-medium">{status.data.active_orders}</dd></div>
            <div><dt className="text-xs text-muted">Entregadores disp./offline</dt><dd className="tabular font-medium">{status.data.available_couriers} / {status.data.offline_couriers}</dd></div>
            {status.data.last_action && <div className="col-span-full text-xs text-muted">Última ação: {status.data.last_action}</div>}
          </dl>
        )}
        {!canWrite && <p className="rounded-lg border border-line bg-bg/40 p-3 text-sm text-muted">Seu perfil é somente leitura: o simulador está desabilitado.</p>}

        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-bg/40 p-3">
          <div><label htmlFor="adv" className="text-xs font-medium text-muted">Avançar relógio</label>
            <Select id="adv" className="mt-1 w-36" value={minutes} onChange={(e) => setMinutes(e.target.value)} disabled={disabled}>{[5, 15, 30, 60, 120].map((m) => <option key={m} value={m}>{m} min</option>)}</Select></div>
          <Button disabled={disabled} loading={advance.isPending} onClick={() => advance.mutate(Number(minutes))}><FastForward className="h-4 w-4" />Avançar</Button>
          <p className="basis-full text-xs text-muted sm:basis-auto">Processa a evolução dos pedidos (confirmação, preparo, retirada, entrega) e atribui entregadores aos pedidos aguardando — regra explícita do simulador (melhor candidato do ranking).</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Action icon={<PackagePlus className="h-4 w-4" />} title="Gerar 5 pedidos" hint="Novos pedidos RECEIVED em restaurantes abertos" onClick={() => act.mutate({ action: 'spawn_orders', count: 5 })} />
          <Action icon={<Flame className="h-4 w-4" />} title="Pico de demanda (15 pedidos)" hint="Simula aumento repentino de volume" onClick={() => act.mutate({ action: 'demand_spike', count: 15 })} />
          <Action icon={<UserMinus className="h-4 w-4" />} title="Reduzir 5 entregadores" hint="Coloca 5 entregadores disponíveis offline" onClick={() => act.mutate({ action: 'reduce_couriers', count: 5 })} />
          <Action icon={<UserPlus className="h-4 w-4" />} title="Restaurar entregadores" hint="Todos os offline voltam a ficar disponíveis" onClick={() => act.mutate({ action: 'restore_couriers' })} />
          <Action icon={<XCircle className="h-4 w-4" />} title="Cancelar 3 pedidos" hint="Cancelamentos simulados em pedidos pré-retirada" onClick={() => act.mutate({ action: 'cancel_orders', count: 3 })} />
          <Action icon={<ShieldAlert className="h-4 w-4" />} title="Gerar ocorrências de atraso" hint="Abre ocorrência para cada pedido atrasado sem ocorrência aberta" onClick={() => act.mutate({ action: 'generate_incidents' })} />
        </div>

        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-bg/40 p-3">
          <div><label htmlFor="sr" className="text-xs font-medium text-muted">Atraso em restaurante</label>
            <Select id="sr" className="mt-1 w-56" value={rest} onChange={(e) => setRest(e.target.value)} disabled={disabled}><option value="">Selecione…</option>{restaurants.data?.items.map((r) => <option key={r.id} value={r.code}>{r.name}</option>)}</Select></div>
          <div><label htmlFor="sf" className="text-xs font-medium text-muted">Fator de preparo</label>
            <Select id="sf" className="mt-1 w-28" value={factor} onChange={(e) => setFactor(e.target.value)} disabled={disabled}>{['1', '1.5', '2', '3'].map((f) => <option key={f} value={f}>×{f}</option>)}</Select></div>
          <Button variant="secondary" disabled={disabled || !rest} loading={act.isPending} onClick={() => act.mutate({ action: 'restaurant_delay', restaurant: rest, factor: Number(factor) })}><Clock className="h-4 w-4" />Aplicar</Button>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
          <p className="text-xs text-muted">Restaurar apaga os dados atuais e recria o conjunto de demonstração original (somente administrador).</p>
          <Button variant="danger" disabled={user?.role !== 'ADMIN'} onClick={() => setConfirmReset(true)}><RotateCcw className="h-4 w-4" />Restaurar demonstração</Button>
        </div>
      </CardContent>
      <Dialog open={confirmReset} onOpenChange={setConfirmReset}>
        <DialogContent title="Restaurar ambiente de demonstração?" description="Todos os pedidos, ocorrências, conversas e alterações serão substituídos pelos dados iniciais.">
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setConfirmReset(false)}>Cancelar</Button><Button variant="danger" loading={reset.isPending} onClick={() => reset.mutate()}>Restaurar</Button></div>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export default function SettingsPage() {
  const rules = useQuery({ queryKey: ['rules'], queryFn: () => get<{ rules: Record<string, number> }>('/settings/rules') })
  const system = useQuery({ queryKey: ['system'], queryFn: () => get<{ environment: string; database: string; token_expire_minutes: number }>('/settings/system') })
  const ai = useQuery({ queryKey: ['ai-status'], queryFn: () => get<AiStatus>('/ai/status') })
  const { user } = useAuth()
  return (
    <>
      <PageHeader title="Configurações" description="Simulação, regras operacionais ativas e informações do ambiente." />
      <div className="space-y-4">
        <SimPanel />
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader><div><CardTitle>Regras operacionais ativas</CardTitle><CardDescription>Camada independente (backend/app/rules); sobrescrevível por RULES_OVERRIDES</CardDescription></div></CardHeader>
            <CardContent>
              {rules.error ? <ErrorState error={rules.error} /> : (
                <dl className="divide-y divide-line text-sm">
                  {Object.entries(rules.data?.rules ?? {}).map(([k, v]) => <div key={k} className="flex items-center justify-between gap-3 py-2"><dt className="text-muted">{RULE_LABEL[k] ?? k}</dt><dd className="tabular font-mono font-medium">{v}</dd></div>)}
                </dl>
              )}
            </CardContent>
          </Card>
          <div className="space-y-4">
            <Card>
              <CardHeader><CardTitle>Ambiente</CardTitle></CardHeader>
              <CardContent><dl className="divide-y divide-line text-sm">
                {[['Usuário', `${user?.full_name} (${user?.email})`], ['Perfil', user?.role], ['Ambiente', system.data?.environment], ['Banco de dados', system.data?.database], ['Expiração do token', `${system.data?.token_expire_minutes} min`]].map(([k, v]) => <div key={k} className="flex justify-between gap-3 py-2"><dt className="text-muted">{k}</dt><dd className="text-right font-medium">{v ?? '—'}</dd></div>)}
              </dl></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Provedor de IA</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p>{ai.data?.label}</p>
                {ai.data && <p className="text-xs text-muted">Limites: {ai.data.limits.max_iterations} iterações · {ai.data.limits.timeout_seconds}s · {ai.data.limits.messages_per_minute} msgs/min · {ai.data.limits.tool_calls_per_turn} ferramentas/turno</p>}
                <p className="text-xs text-muted">Configure via variáveis de ambiente do backend (AI_PROVIDER, ANTHROPIC_API_KEY, ANTHROPIC_MODEL). Chaves nunca passam pelo navegador.</p>
              </CardContent>
            </Card>
          </div>
        </div>
        <p className="text-center text-[11px] text-muted">OpsPilot AI é um projeto independente de demonstração tecnológica. Não é afiliado a nenhuma empresa de delivery; todos os dados são fictícios.</p>
      </div>
    </>
  )
}
