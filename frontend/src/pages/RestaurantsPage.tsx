import { useQuery } from '@tanstack/react-query'
import { Star, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { OrderDrawer } from '@/components/OrderDrawer'
import { SituationBadge, StatusBadge } from '@/components/badges'
import { EmptyState, ErrorState, LoadingRows, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select } from '@/components/ui/field'
import { usePeriod } from '@/hooks/usePeriod'
import { get } from '@/lib/api'
import { fmtMin, fmtTime, STATUS_LABEL } from '@/lib/format'
import type { Restaurant, RestaurantDetail } from '@/types/api'

function Detail({ code, hours, onClose }: { code: string | null; hours: number; onClose: () => void }) {
  const [order, setOrder] = useState<string | null>(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['restaurant', code, hours], queryFn: () => get<RestaurantDetail>(`/restaurants/${code}`, { period_hours: hours }), enabled: !!code })
  return (
    <>
      <Dialog open={!!code} onOpenChange={(o) => !o && onClose()}>
        <DialogContent title={data?.name ?? 'Restaurante'} description="Desempenho no período selecionado e pedidos relacionados">
          {isLoading && <LoadingRows rows={4} />}{error && <ErrorState error={error} />}
          {data && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2"><StatusBadge status={data.status} /><Badge>{data.category}</Badge>{data.prep_alert && <Badge tone="warn">Preparo {data.prep_alert_pct?.toFixed(0)}% acima da média</Badge>}</div>
              <p className="text-sm text-muted">{data.address} (endereço fictício)</p>
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div><dt className="text-xs text-muted">Pedidos</dt><dd className="tabular text-lg font-semibold">{data.orders}</dd></div>
                <div><dt className="text-xs text-muted">Preparo médio</dt><dd className="tabular text-lg font-semibold">{fmtMin(data.avg_prep_minutes)}</dd></div>
                <div><dt className="text-xs text-muted">Cancelamento</dt><dd className="tabular text-lg font-semibold">{data.cancellation_rate}%</dd></div>
                <div><dt className="text-xs text-muted">Atrasados</dt><dd className="tabular text-lg font-semibold">{data.delayed_orders}</dd></div>
              </dl>
              <p className="text-xs text-muted">Média da operação: {fmtMin(data.operation_avg_prep_minutes)} · preparo nominal do restaurante: {fmtMin(data.baseline_prep_minutes)}</p>
              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Pedidos relacionados</h4>
                <ul className="divide-y divide-line rounded-lg border border-line text-sm">
                  {data.recent_orders.slice(0, 12).map((o) => (
                    <li key={o.id}><button className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left hover:bg-surface-2/60" onClick={() => setOrder(o.code)}>
                      <span className="font-mono text-xs text-accent">{o.code}</span><span className="min-w-0 flex-1 truncate text-muted">{o.customer_name}</span>
                      <StatusBadge status={o.status} /><SituationBadge situation={o.situation} /><span className="tabular text-xs text-muted">{fmtTime(o.created_at)}</span>
                    </button></li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <OrderDrawer code={order} onClose={() => setOrder(null)} />
    </>
  )
}

export default function RestaurantsPage() {
  const { hours, label } = usePeriod()
  const [status, setStatus] = useState('')
  const [slowOnly, setSlowOnly] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['restaurants', status, hours], queryFn: () => get<{ items: Restaurant[]; operation_avg_prep_minutes: number | null }>('/restaurants', { status, period_hours: hours }),
  })
  const items = (data?.items ?? []).filter((r) => !slowOnly || r.prep_alert)

  return (
    <>
      <PageHeader title="Restaurantes" description={`${label} · desempenho calculado a partir dos pedidos (restaurantes fictícios)`}
        actions={<>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted"><input type="checkbox" checked={slowOnly} onChange={(e) => setSlowOnly(e.target.checked)} className="accent-[#6366F1]" />Somente preparo acima da média</label>
          <label htmlFor="rs" className="sr-only">Status</label>
          <Select id="rs" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Todos os status</option>{['OPEN', 'BUSY', 'PAUSED', 'CLOSED'].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select>
        </>} />
      {data && <Card className="mb-4"><CardContent className="flex items-center gap-3 pt-4 text-sm"><TrendingUp className="h-4 w-4 text-accent" />Tempo médio de preparação da operação: <b className="tabular">{fmtMin(data.operation_avg_prep_minutes)}</b></CardContent></Card>}
      <Card className="overflow-hidden">
        {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : isLoading ? <LoadingRows /> : !items.length ? <EmptyState title="Nenhum restaurante encontrado" hint="Remova os filtros para ver todos." /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <caption className="sr-only">Restaurantes e desempenho</caption>
              <thead className="border-b border-line text-left text-xs text-muted"><tr>{['Restaurante', 'Categoria', 'Status', 'Pedidos', 'Preparo médio', 'vs. média', 'Cancelamento', 'Atrasados', 'Avaliação', ''].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {items.map((r) => (
                  <tr key={r.id} className="hover:bg-surface-2/50">
                    <td className="px-4 py-2.5"><span className="font-medium">{r.name}</span> <span className="font-mono text-[10px] text-muted">{r.code}</span></td>
                    <td className="px-4 py-2.5 text-muted">{r.category}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={r.status} /></td>
                    <td className="tabular px-4 py-2.5">{r.orders}</td>
                    <td className="tabular px-4 py-2.5">{fmtMin(r.avg_prep_minutes)}</td>
                    <td className="tabular px-4 py-2.5">{r.vs_operation_avg_pct == null ? '—' : <span className={r.prep_alert ? 'font-medium text-warn' : 'text-muted'}>{r.vs_operation_avg_pct > 0 ? '+' : ''}{r.vs_operation_avg_pct.toFixed(0)}%</span>}</td>
                    <td className="tabular px-4 py-2.5">{r.cancellation_rate}%</td>
                    <td className="tabular px-4 py-2.5">{r.delayed_orders}</td>
                    <td className="px-4 py-2.5"><span className="inline-flex items-center gap-1 text-muted"><Star className="h-3.5 w-3.5 fill-warn text-warn" aria-hidden />{r.rating}</span></td>
                    <td className="px-4 py-2.5 text-right"><Button size="sm" variant="outline" onClick={() => setSelected(r.code)}>Detalhes</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Detail code={selected} hours={hours} onClose={() => setSelected(null)} />
    </>
  )
}
