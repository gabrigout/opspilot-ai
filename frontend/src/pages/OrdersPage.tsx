import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { OrderDrawer } from '@/components/OrderDrawer'
import { SituationBadge, StatusBadge } from '@/components/badges'
import { EmptyState, ErrorState, LoadingRows, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { get } from '@/lib/api'
import { fmtMoney, fmtTime, SITUATION_LABEL, STATUS_LABEL } from '@/lib/format'
import type { OrderSummary, Page, Restaurant } from '@/types/api'

const PAGE_SIZE = 15

export default function OrdersPage() {
  const [params, setParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const f = {
    q: params.get('q') ?? '', status: params.get('status') ?? '', restaurant: params.get('restaurant') ?? '',
    situation: params.get('situation') ?? '', period_hours: params.get('period_hours') ?? '',
  }
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v); else next.delete(k)
    setParams(next, { replace: true })
    setPage(1)
  }
  const hasFilters = Object.values(f).some(Boolean)

  const restaurants = useQuery({ queryKey: ['restaurants-lite'], queryFn: () => get<{ items: Restaurant[] }>('/restaurants', { period_hours: 24 }), staleTime: 300_000 })
  const { data, error, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['orders', f, page], placeholderData: keepPreviousData,
    queryFn: () => get<Page<OrderSummary>>('/orders', { ...f, page, page_size: PAGE_SIZE }),
  })
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader title="Monitoramento de pedidos" description="Busque, filtre e acompanhe o ciclo de vida dos pedidos em tempo real (dados simulados)." />
      <Card className="mb-4 p-3 sm:p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="relative lg:col-span-2">
            <label className="sr-only" htmlFor="f-q">Buscar por código</label>
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden />
            <Input id="f-q" className="pl-9" placeholder="Buscar por código (ex.: 1042)" value={f.q} onChange={(e) => set('q', e.target.value)} />
          </div>
          <div>
            <label className="sr-only" htmlFor="f-status">Status</label>
            <Select id="f-status" value={f.status} onChange={(e) => set('status', e.target.value)}>
              <option value="">Todos os status</option>
              {Object.keys(STATUS_LABEL).slice(0, 8).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </Select>
          </div>
          <div>
            <label className="sr-only" htmlFor="f-situation">Situação</label>
            <Select id="f-situation" value={f.situation} onChange={(e) => set('situation', e.target.value)}>
              <option value="">Qualquer situação</option>
              {['delayed', 'at_risk', 'on_track'].map((s) => <option key={s} value={s}>{SITUATION_LABEL[s]}</option>)}
            </Select>
          </div>
          <div>
            <label className="sr-only" htmlFor="f-rest">Restaurante</label>
            <Select id="f-rest" value={f.restaurant} onChange={(e) => set('restaurant', e.target.value)}>
              <option value="">Todos os restaurantes</option>
              {restaurants.data?.items.map((r) => <option key={r.id} value={r.code}>{r.name}</option>)}
            </Select>
          </div>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="f-period">Criados em</label>
            <Select id="f-period" value={f.period_hours} onChange={(e) => set('period_hours', e.target.value)}>
              <option value="">Qualquer data</option>
              <option value="6">Últimas 6 h</option><option value="24">Últimas 24 h</option><option value="72">Últimos 3 dias</option><option value="168">Últimos 7 dias</option>
            </Select>
            {hasFilters && <Button variant="ghost" size="icon" aria-label="Limpar filtros" onClick={() => { setParams({}, { replace: true }); setPage(1) }}><X className="h-4 w-4" /></Button>}
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : isLoading ? <LoadingRows rows={8} /> : !data?.items.length ? (
          <EmptyState title="Nenhum pedido encontrado" hint="Ajuste os filtros ou gere novos pedidos pela simulação (Configurações)." />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : ''}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <caption className="sr-only">Lista de pedidos</caption>
                <thead className="border-b border-line text-left text-xs text-muted">
                  <tr>{['Pedido', 'Restaurante', 'Cliente', 'Status', 'Situação', 'Entregador', 'Prazo', 'Valor'].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.items.map((o) => (
                    <tr key={o.id} className="cursor-pointer hover:bg-surface-2/50" onClick={() => setSelected(o.code)}>
                      <td className="px-4 py-2.5"><button className="cursor-pointer font-mono text-xs text-accent hover:underline" onClick={(e) => { e.stopPropagation(); setSelected(o.code) }}>{o.code}</button></td>
                      <td className="px-4 py-2.5">{o.restaurant.name}</td>
                      <td className="px-4 py-2.5 text-muted">{o.customer_name}</td>
                      <td className="px-4 py-2.5"><StatusBadge status={o.status} /></td>
                      <td className="px-4 py-2.5">
                        <SituationBadge situation={o.situation} />
                        {o.is_delayed && <span className="ml-1.5 text-xs text-[#ff8585]">+{Math.round(o.delay_minutes)} min</span>}
                      </td>
                      <td className="px-4 py-2.5 text-muted">{o.courier ? o.courier.code : <span className="text-warn">sem entregador</span>}</td>
                      <td className="tabular px-4 py-2.5 text-muted">{fmtTime(o.promised_at)}</td>
                      <td className="tabular px-4 py-2.5">{fmtMoney(o.total_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-muted">
              <span>{data.total} pedido(s) · página {data.page} de {pages}</span>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" aria-label="Página anterior" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}><ChevronLeft className="h-4 w-4" /></Button>
                <Button variant="outline" size="sm" aria-label="Próxima página" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}><ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          </div>
        )}
      </Card>
      <OrderDrawer code={selected} onClose={() => setSelected(null)} />
    </>
  )
}
