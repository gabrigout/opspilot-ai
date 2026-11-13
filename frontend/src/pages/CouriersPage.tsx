import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { OrderDrawer } from '@/components/OrderDrawer'
import { SituationBadge, StatusBadge } from '@/components/badges'
import { EmptyState, ErrorState, LoadingRows, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select } from '@/components/ui/field'
import { useAuth } from '@/hooks/useAuth'
import { useAction } from '@/hooks/useMutationToast'
import { get, patch } from '@/lib/api'
import { fmtMin, fmtTime, STATUS_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Courier, CourierDetail, CourierStatus } from '@/types/api'

const STATUSES: CourierStatus[] = ['AVAILABLE', 'ASSIGNED', 'PICKING_UP', 'DELIVERING', 'OFFLINE']

function CourierDialog({ code, onClose }: { code: string | null; onClose: () => void }) {
  const { canWrite } = useAuth()
  const [order, setOrder] = useState<string | null>(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['courier', code], queryFn: () => get<CourierDetail>(`/couriers/${code}`), enabled: !!code })
  const setStatus = useAction((status: CourierStatus) => patch(`/couriers/${code}/status`, { status }), { success: 'Status do entregador atualizado' })
  return (
    <>
      <Dialog open={!!code} onOpenChange={(o) => !o && onClose()}>
        <DialogContent title={data ? `${data.code} · ${data.name}` : 'Entregador'} description="Disponibilidade, pedidos associados e histórico">
          {isLoading && <LoadingRows rows={4} />}
          {error && <ErrorState error={error} />}
          {data && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3"><StatusBadge status={data.status} />
                <span className="text-xs text-muted">Localização simulada: {data.location.lat}, {data.location.lng}</span></div>
              <dl className="grid grid-cols-3 gap-3 text-sm">
                <div><dt className="text-xs text-muted">Entregas</dt><dd className="tabular text-lg font-semibold">{data.total_deliveries}</dd></div>
                <div><dt className="text-xs text-muted">Tempo médio</dt><dd className="tabular text-lg font-semibold">{fmtMin(data.avg_delivery_minutes)}</dd></div>
                <div><dt className="text-xs text-muted">Pedidos ativos</dt><dd className="tabular text-lg font-semibold">{data.active_orders}</dd></div>
              </dl>
              {canWrite && (
                <div>
                  <label htmlFor="c-status" className="text-xs font-medium text-muted">Atualizar status</label>
                  <Select id="c-status" className="mt-1" value={data.status} disabled={setStatus.isPending} onChange={(e) => setStatus.mutate(e.target.value as CourierStatus)}>
                    {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                  </Select>
                  <p className="mt-1 text-[11px] text-muted">Entregadores com pedidos ativos não podem ficar Disponíveis/Offline; status ocupados exigem um pedido ativo.</p>
                </div>
              )}
              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Pedidos associados (recentes)</h4>
                {data.recent_orders.length === 0 ? <p className="text-sm text-muted">Sem pedidos associados.</p> : (
                  <ul className="divide-y divide-line rounded-lg border border-line text-sm">
                    {data.recent_orders.map((o) => (
                      <li key={o.id}>
                        <button className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left hover:bg-surface-2/60" onClick={() => setOrder(o.code)}>
                          <span className="font-mono text-xs text-accent">{o.code}</span>
                          <span className="min-w-0 flex-1 truncate text-muted">{o.restaurant.name}</span>
                          <StatusBadge status={o.status} /><SituationBadge situation={o.situation} />
                          <span className="tabular text-xs text-muted">{fmtTime(o.created_at)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <OrderDrawer code={order} onClose={() => setOrder(null)} />
    </>
  )
}

export default function CouriersPage() {
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['couriers', status], queryFn: () => get<{ items: Courier[]; total: number; summary: Record<string, number> }>('/couriers', { status }),
  })
  const available = data?.summary.AVAILABLE ?? 0

  return (
    <>
      <PageHeader title="Central de entregadores" description="Disponibilidade, carga operacional e histórico dos entregadores (localização simulada)."
        actions={<><label htmlFor="cs" className="sr-only">Filtrar por status</label>
          <Select id="cs" value={status} onChange={(e) => setStatus(e.target.value)} className="w-48"><option value="">Todos os status</option>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select></>} />
      {data && available === 0 && (
        <div role="alert" className="mb-4 flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-[#ff9a9a]">
          <AlertTriangle className="h-4 w-4 shrink-0" /> Nenhum entregador disponível: alerta de capacidade ativo.
        </div>
      )}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {STATUSES.map((s) => (
          <button key={s} onClick={() => setStatus(status === s ? '' : s)} className="cursor-pointer text-left" aria-pressed={status === s}>
            <Card className={cn('transition-colors hover:border-primary/50', status === s && 'border-primary')}>
              <CardContent className="pt-3"><p className="text-xs text-muted">{STATUS_LABEL[s]}</p><p className="tabular text-2xl font-semibold">{data?.summary[s] ?? 0}</p></CardContent>
            </Card>
          </button>
        ))}
      </div>
      <Card className="overflow-hidden">
        <CardHeader className="pb-0"><CardTitle>Entregadores {data && <span className="font-normal text-muted">({data.total})</span>}</CardTitle></CardHeader>
        {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : isLoading ? <LoadingRows /> : !data?.items.length ? <EmptyState title="Nenhum entregador neste filtro" /> : (
          <div className="overflow-x-auto">
            <table className="mt-3 w-full min-w-[760px] text-sm">
              <caption className="sr-only">Lista de entregadores</caption>
              <thead className="border-y border-line text-left text-xs text-muted"><tr>{['ID', 'Nome', 'Status', 'Pedidos ativos', 'Entregas', 'Tempo médio', 'Última atualização', ''].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {data.items.map((c) => (
                  <tr key={c.id} className="hover:bg-surface-2/50">
                    <td className="px-4 py-2.5 font-mono text-xs text-accent">{c.code}</td>
                    <td className="px-4 py-2.5">{c.name}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={c.status} /></td>
                    <td className="tabular px-4 py-2.5">{c.active_orders}</td>
                    <td className="tabular px-4 py-2.5">{c.total_deliveries}</td>
                    <td className="tabular px-4 py-2.5">{fmtMin(c.avg_delivery_minutes)}</td>
                    <td className="tabular px-4 py-2.5 text-muted">{fmtTime(c.updated_at)}</td>
                    <td className="px-4 py-2.5 text-right"><Button size="sm" variant="outline" onClick={() => setSelected(c.code)}>Detalhes</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <CourierDialog code={selected} onClose={() => setSelected(null)} />
    </>
  )
}
