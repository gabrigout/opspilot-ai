import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingRows, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Select } from '@/components/ui/field'
import { get } from '@/lib/api'
import { fmtDateTime } from '@/lib/format'
import type { Activity, Page } from '@/types/api'

const SIZE = 25
const TONE = { INFO: 'accent', WARNING: 'warn', CRITICAL: 'danger' } as const
const SEV = { INFO: 'Info', WARNING: 'Atenção', CRITICAL: 'Crítico' } as const

export default function ActivityPage() {
  const [severity, setSeverity] = useState('')
  const [entity, setEntity] = useState('')
  const [page, setPage] = useState(1)
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['activity', severity, entity, page], placeholderData: keepPreviousData,
    queryFn: () => get<Page<Activity>>('/activity', { severity, entity_type: entity, page, page_size: SIZE }),
  })
  const pages = data ? Math.max(1, Math.ceil(data.total / SIZE)) : 1
  return (
    <>
      <PageHeader title="Histórico de atividades" description="Trilha de eventos operacionais registrados pelo sistema, pelo simulador e pelos usuários."
        actions={<>
          <label htmlFor="a-sev" className="sr-only">Severidade</label>
          <Select id="a-sev" className="w-40" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1) }}><option value="">Toda severidade</option><option value="INFO">Info</option><option value="WARNING">Atenção</option><option value="CRITICAL">Crítico</option></Select>
          <label htmlFor="a-ent" className="sr-only">Entidade</label>
          <Select id="a-ent" className="w-40" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1) }}><option value="">Toda entidade</option><option value="order">Pedidos</option><option value="incident">Ocorrências</option><option value="courier">Entregadores</option><option value="restaurant">Restaurantes</option></Select>
        </>} />
      <Card className="overflow-hidden">
        {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : isLoading ? <LoadingRows rows={10} /> : !data?.items.length ? <EmptyState title="Nenhuma atividade registrada" hint="Altere filtros ou avance a simulação para gerar eventos." /> : (
          <>
            <ul className="divide-y divide-line">
              {data.items.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
                  <Badge tone={TONE[a.severity]}>{SEV[a.severity]}</Badge>
                  <span className="min-w-0 flex-1">{a.message}</span>
                  <span className="text-xs text-muted">{a.actor}</span>
                  <span className="tabular w-28 text-right text-xs text-muted">{fmtDateTime(a.created_at)}</span>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-muted">
              <span>{data.total} evento(s) · página {page} de {pages}</span>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" aria-label="Página anterior" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}><ChevronLeft className="h-4 w-4" /></Button>
                <Button variant="outline" size="sm" aria-label="Próxima página" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}><ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  )
}
