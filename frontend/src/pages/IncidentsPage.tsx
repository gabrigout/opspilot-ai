import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { IncidentFormDialog } from '@/components/IncidentForm'
import { OrderDrawer } from '@/components/OrderDrawer'
import { PriorityBadge, StatusBadge } from '@/components/badges'
import { EmptyState, ErrorState, LoadingRows, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Field, Input, Select, Textarea } from '@/components/ui/field'
import { useAuth } from '@/hooks/useAuth'
import { useAction } from '@/hooks/useMutationToast'
import { get, patch } from '@/lib/api'
import { fmtDateTime, INCIDENT_TYPE_LABEL, PRIORITY_LABEL, STATUS_LABEL } from '@/lib/format'
import type { Incident, IncidentDetail } from '@/types/api'

const schema = z.object({
  status: z.string(), priority: z.string(),
  assignee: z.string().trim().max(120),
  resolution: z.string().trim().max(2000),
}).refine((v) => !['RESOLVED', 'CLOSED'].includes(v.status) || v.resolution.length >= 3, { path: ['resolution'], message: 'Registre a resolução para resolver/fechar' })
type Form = z.infer<typeof schema>

function IncidentDialog({ code, onClose }: { code: string | null; onClose: () => void }) {
  const { canWrite } = useAuth()
  const [order, setOrder] = useState<string | null>(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['incident', code], queryFn: () => get<IncidentDetail>(`/incidents/${code}`), enabled: !!code })
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Form>({ resolver: zodResolver(schema) })
  useEffect(() => { if (data) reset({ status: data.status, priority: data.priority, assignee: data.assignee ?? '', resolution: data.resolution ?? '' }) }, [data, reset])
  const update = useAction((v: Form) => patch<IncidentDetail>(`/incidents/${code}`, { status: v.status, priority: v.priority, assignee: v.assignee || undefined, resolution: v.resolution || undefined }),
    { success: 'Ocorrência atualizada' })
  const closed = data?.status === 'CLOSED'

  return (
    <>
      <Dialog open={!!code} onOpenChange={(o) => !o && onClose()}>
        <DialogContent side="right" title={data ? `${data.code} · ${data.title}` : 'Ocorrência'} description="Detalhes, atualização e histórico de alterações">
          {isLoading && <LoadingRows rows={4} />}{error && <ErrorState error={error} />}
          {data && (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2"><StatusBadge status={data.status} /><PriorityBadge priority={data.priority} />
                {data.order && <button className="cursor-pointer rounded bg-surface-2 px-2 py-0.5 font-mono text-xs text-accent hover:underline" onClick={() => setOrder(data.order!.code)}>{data.order.code}</button>}
                {data.restaurant && <span className="text-xs text-muted">{data.restaurant.name}</span>}</div>
              <p className="whitespace-pre-wrap text-sm">{data.description}</p>
              <p className="text-xs text-muted">Aberta em {fmtDateTime(data.created_at)} por {data.created_by}</p>
              {canWrite && (closed ? <p className="rounded-lg border border-line bg-bg/40 p-3 text-sm text-muted">Ocorrência fechada: não pode mais ser alterada.</p> : (
                <form onSubmit={handleSubmit((v) => update.mutate(v))} noValidate className="space-y-3 rounded-lg border border-line bg-bg/40 p-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Status" htmlFor="i-status"><Select id="i-status" {...register('status')}>{['OPEN', 'INVESTIGATING', 'WAITING_ACTION', 'RESOLVED', 'CLOSED'].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select></Field>
                    <Field label="Prioridade" htmlFor="i-prio"><Select id="i-prio" {...register('priority')}>{Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
                  </div>
                  <Field label="Responsável" htmlFor="i-assignee"><Input id="i-assignee" {...register('assignee')} /></Field>
                  <Field label="Resolução" htmlFor="i-res" error={errors.resolution?.message}><Textarea id="i-res" rows={3} {...register('resolution')} /></Field>
                  <Button type="submit" loading={update.isPending}>Salvar alterações</Button>
                </form>
              ))}
              {data.resolution && !canWrite && <p className="text-sm"><b>Resolução:</b> {data.resolution}</p>}
              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Histórico de alterações</h4>
                <ol className="relative space-y-3 border-l border-line pl-4">
                  {data.history.map((h) => (
                    <li key={h.id} className="relative text-sm"><span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-accent" aria-hidden />
                      <p>{h.message}</p><p className="text-xs text-muted">{fmtDateTime(h.created_at)} · {h.actor}</p></li>
                  ))}
                </ol>
              </section>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <OrderDrawer code={order} onClose={() => setOrder(null)} />
    </>
  )
}

export default function IncidentsPage() {
  const { canWrite } = useAuth()
  const [f, setF] = useState({ status: '', priority: '', open_only: false })
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['incidents', f], queryFn: () => get<{ items: Incident[]; total: number }>('/incidents', { status: f.status, priority: f.priority, open_only: f.open_only || undefined }),
  })
  return (
    <>
      <PageHeader title="Central de ocorrências" description="Registre, acompanhe e resolva problemas operacionais, com histórico completo de alterações."
        actions={canWrite ? <Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />Nova ocorrência</Button> : undefined} />
      <Card className="mb-4 flex flex-wrap items-center gap-3 p-3 sm:p-4">
        <label htmlFor="if-status" className="sr-only">Status</label>
        <Select id="if-status" className="w-48" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}><option value="">Todos os status</option>{['OPEN', 'INVESTIGATING', 'WAITING_ACTION', 'RESOLVED', 'CLOSED'].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select>
        <label htmlFor="if-prio" className="sr-only">Prioridade</label>
        <Select id="if-prio" className="w-44" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}><option value="">Qualquer prioridade</option>{Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted"><input type="checkbox" className="accent-[#6366F1]" checked={f.open_only} onChange={(e) => setF({ ...f, open_only: e.target.checked })} />Somente abertas</label>
        {data && <span className="ml-auto text-xs text-muted">{data.total} ocorrência(s)</span>}
      </Card>
      <Card className="overflow-hidden">
        {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : isLoading ? <LoadingRows /> : !data?.items.length ? (
          <EmptyState title="Nenhuma ocorrência encontrada" hint="Crie uma nova ocorrência ou ajuste os filtros." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <caption className="sr-only">Ocorrências</caption>
              <thead className="border-b border-line text-left text-xs text-muted"><tr>{['Código', 'Tipo', 'Prioridade', 'Status', 'Pedido', 'Responsável', 'Aberta em'].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {data.items.map((i) => (
                  <tr key={i.id} className="cursor-pointer hover:bg-surface-2/50" onClick={() => setSelected(i.code)}>
                    <td className="px-4 py-2.5"><button className="cursor-pointer font-mono text-xs text-accent hover:underline" onClick={(e) => { e.stopPropagation(); setSelected(i.code) }}>{i.code}</button></td>
                    <td className="px-4 py-2.5">{INCIDENT_TYPE_LABEL[i.type] ?? i.type}</td>
                    <td className="px-4 py-2.5"><PriorityBadge priority={i.priority} /></td>
                    <td className="px-4 py-2.5"><StatusBadge status={i.status} /></td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted">{i.order?.code ?? '—'}</td>
                    <td className="px-4 py-2.5 text-muted">{i.assignee ?? <span className="text-warn">sem responsável</span>}</td>
                    <td className="tabular px-4 py-2.5 text-muted">{fmtDateTime(i.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <IncidentDialog code={selected} onClose={() => setSelected(null)} />
      {creating && <IncidentFormDialog open={creating} onOpenChange={setCreating} />}
    </>
  )
}
