import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Bike, Check, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { IncidentFormDialog } from '@/components/IncidentForm'
import { PriorityBadge, SituationBadge, StatusBadge } from '@/components/badges'
import { ErrorState, LoadingRows } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/field'
import { useAuth } from '@/hooks/useAuth'
import { useAction } from '@/hooks/useMutationToast'
import { get, patch, post } from '@/lib/api'
import { fmtDateTime, fmtMoney, label, STATUS_LABEL } from '@/lib/format'
import type { OrderDetail, OrderStatus, Recommendation } from '@/types/api'

const PRE_PICKUP: OrderStatus[] = ['RECEIVED', 'CONFIRMED', 'PREPARING', 'READY_FOR_PICKUP', 'WAITING_COURIER']

function Recommendations({ order }: { order: OrderDetail }) {
  const { canWrite } = useAuth()
  const [confirm, setConfirm] = useState<string | null>(null)
  const { data, isLoading, error } = useQuery({
    queryKey: ['recommend', order.code, order.courier?.code], queryFn: () => get<Recommendation>(`/orders/${order.code}/courier-recommendations`, { limit: 5 }),
  })
  const assign = useAction((courier_id: string) => post(`/orders/${order.code}/assign`, { courier_id }), {
    success: 'Entregador atribuído', onSuccess: () => setConfirm(null),
  })
  if (isLoading) return <LoadingRows rows={3} />
  if (error) return <ErrorState error={error} />
  if (!data?.candidates.length) return <p className="text-sm text-muted">Nenhum entregador elegível (disponível e a menos de 8 km do restaurante).</p>
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted">Ranking calculado por distância, carga e ociosidade. <b className="text-fg">Nada é atribuído automaticamente.</b></p>
      <ol className="space-y-2">
        {data.candidates.map((c, i) => (
          <li key={c.courier.id} className="rounded-lg border border-line bg-bg/40 p-3">
            <div className="flex items-center gap-2">
              <span className="grid h-5 w-5 place-items-center rounded-full bg-primary/20 text-[11px] font-semibold text-[#a5a8ff]">{i + 1}</span>
              <span className="font-mono text-xs text-accent">{c.courier.code}</span>
              <span className="min-w-0 flex-1 truncate text-sm">{c.courier.name}</span>
              <span className="tabular rounded bg-surface-2 px-1.5 py-0.5 text-xs font-semibold">{c.score} pts</span>
            </div>
            <p className="mt-1 text-xs text-muted">{c.reasons.join(' · ')}</p>
            {canWrite && (confirm === c.courier.code ? (
              <div className="mt-2 flex items-center gap-2">
                <Button size="sm" loading={assign.isPending} onClick={() => assign.mutate(c.courier.code)}><Check className="h-3.5 w-3.5" />Confirmar atribuição</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirm(null)}>Cancelar</Button>
              </div>
            ) : (
              <Button size="sm" variant="outline" className="mt-2" onClick={() => setConfirm(c.courier.code)}>Atribuir {c.courier.code}</Button>
            ))}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function OrderDrawer({ code, onClose }: { code: string | null; onClose: () => void }) {
  const { canWrite } = useAuth()
  const [cancelling, setCancelling] = useState(false)
  const [reason, setReason] = useState('')
  const [incidentOpen, setIncidentOpen] = useState(false)
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['order', code], queryFn: () => get<OrderDetail>(`/orders/${code}`), enabled: !!code })
  const change = useAction((v: { status: OrderStatus; reason?: string }) => patch<OrderDetail>(`/orders/${code}/status`, v), {
    success: 'Status atualizado', onSuccess: () => { setCancelling(false); setReason('') },
  })

  return (
    <Dialog open={!!code} onOpenChange={(o) => !o && onClose()}>
      <DialogContent side="right" title={code ? `Pedido ${code}` : 'Pedido'} description="Detalhes, histórico e ações do pedido">
        {isLoading && <LoadingRows />}
        {error && <ErrorState error={error} onRetry={() => void refetch()} />}
        {data && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={data.status} /><SituationBadge situation={data.situation} />
              {data.is_delayed && <PriorityBadge priority={data.delay_priority} />}
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <div><dt className="text-xs text-muted">Restaurante</dt><dd>{data.restaurant.name}</dd></div>
              <div><dt className="text-xs text-muted">Cliente (fictício)</dt><dd>{data.customer.name}</dd></div>
              <div className="col-span-2"><dt className="text-xs text-muted">Endereço de entrega (fictício)</dt><dd>{data.customer.address}</dd></div>
              <div><dt className="text-xs text-muted">Criado</dt><dd>{fmtDateTime(data.created_at)}</dd></div>
              <div><dt className="text-xs text-muted">Prazo prometido</dt><dd>{fmtDateTime(data.promised_at)}</dd></div>
              <div><dt className="text-xs text-muted">Preparo estimado</dt><dd>{data.est_prep_minutes} min</dd></div>
              <div><dt className="text-xs text-muted">Entrega estimada</dt><dd>{data.est_delivery_minutes} min</dd></div>
              <div><dt className="text-xs text-muted">Entregador</dt><dd>{data.courier ? `${data.courier.code} · ${data.courier.name}` : 'Não atribuído'}</dd></div>
              <div><dt className="text-xs text-muted">Valor</dt><dd>{fmtMoney(data.total_amount)}</dd></div>
            </dl>

            {(data.is_delayed || data.at_risk) && (
              <div className={`rounded-lg border p-3 text-sm ${data.is_delayed ? 'border-danger/40 bg-danger/5' : 'border-warn/40 bg-warn/5'}`}>
                <p className="flex items-center gap-2 font-medium"><AlertTriangle className="h-4 w-4" />{data.is_delayed ? `Atrasado há ${Math.round(data.delay_minutes)} min` : 'Risco de atraso'}</p>
                {data.risk_reasons.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs text-muted">{data.risk_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
              </div>
            )}

            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Itens</h4>
              <ul className="divide-y divide-line rounded-lg border border-line text-sm">
                {data.items.map((i) => <li key={i.name} className="flex justify-between px-3 py-2"><span>{i.quantity}× {i.name}</span><span className="tabular text-muted">{fmtMoney(i.quantity * i.unit_price)}</span></li>)}
              </ul>
            </section>

            {canWrite && (
              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Ações</h4>
                {data.allowed_transitions.length === 0 ? <p className="text-sm text-muted">Pedido em estado final: nenhuma transição disponível.</p> : (
                  <div className="flex flex-wrap gap-2">
                    {data.allowed_transitions.filter((s) => s !== 'CANCELLED').map((s) => (
                      <Button key={s} size="sm" variant="secondary" loading={change.isPending && change.variables?.status === s}
                        disabled={s === 'IN_DELIVERY' && !data.courier} title={s === 'IN_DELIVERY' && !data.courier ? 'Atribua um entregador primeiro' : undefined}
                        onClick={() => change.mutate({ status: s })}>
                        Mover para {label(STATUS_LABEL, s)}
                      </Button>
                    ))}
                    {data.allowed_transitions.includes('CANCELLED') && <Button size="sm" variant="danger" onClick={() => setCancelling(true)}>Cancelar pedido</Button>}
                  </div>
                )}
                {cancelling && (
                  <div className="mt-3 space-y-2 rounded-lg border border-danger/40 bg-danger/5 p-3">
                    <p className="text-sm">Confirmar cancelamento de {data.code}? Esta ação não pode ser desfeita.</p>
                    <Input aria-label="Motivo do cancelamento" placeholder="Motivo (opcional)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} />
                    <div className="flex gap-2">
                      <Button size="sm" variant="danger" loading={change.isPending} onClick={() => change.mutate({ status: 'CANCELLED', reason: reason || undefined })}>Confirmar cancelamento</Button>
                      <Button size="sm" variant="ghost" onClick={() => setCancelling(false)}>Voltar</Button>
                    </div>
                  </div>
                )}
                <Button size="sm" variant="outline" className="mt-3" onClick={() => setIncidentOpen(true)}><Plus className="h-3.5 w-3.5" />Abrir ocorrência</Button>
              </section>
            )}

            {PRE_PICKUP.includes(data.status) && (
              <section>
                <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Sparkles className="h-3.5 w-3.5 text-accent" /><Bike className="h-3.5 w-3.5" />Recomendação de entregador</h4>
                <Recommendations order={data} />
              </section>
            )}

            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Histórico de eventos</h4>
              <ol className="relative space-y-3 border-l border-line pl-4">
                {data.history.map((e) => (
                  <li key={e.id} className="relative text-sm">
                    <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-primary" aria-hidden />
                    <p>{e.message}</p>
                    <p className="text-xs text-muted">{fmtDateTime(e.created_at)} · {e.actor}</p>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </DialogContent>
      {data && <IncidentFormDialog open={incidentOpen} onOpenChange={setIncidentOpen} orderRef={data.code} defaults={{ type: data.is_delayed ? 'DELIVERY_DELAY' : 'CUSTOMER_COMPLAINT', priority: data.delay_priority ?? 'MEDIUM' }} />}
    </Dialog>
  )
}
