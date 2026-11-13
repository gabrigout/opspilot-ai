import { useQuery } from '@tanstack/react-query'
import { Download, FileText, Lightbulb, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { EmptyState, ErrorState, LoadingRows, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { usePeriod } from '@/hooks/usePeriod'
import { download, errorMessage, get } from '@/lib/api'
import { fmtDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Report } from '@/types/api'

export default function ReportsPage() {
  const { hours, label } = usePeriod()
  const [kind, setKind] = useState('general')
  const [busy, setBusy] = useState<string | null>(null)
  const kinds = useQuery({ queryKey: ['report-kinds'], queryFn: () => get<{ items: { kind: string; title: string }[] }>('/reports'), staleTime: Infinity })
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['report', kind, hours], queryFn: () => get<Report>(`/reports/${kind}`, { hours }) })

  const exportAs = async (format: 'csv' | 'pdf') => {
    setBusy(format)
    try { await download(`/reports/${kind}/export`, { format, hours }, `opspilot-${kind}.${format}`); toast.success(`Relatório exportado em ${format.toUpperCase()}`) }
    catch (e) { toast.error(errorMessage(e)) } finally { setBusy(null) }
  }

  return (
    <>
      <PageHeader title="Relatórios operacionais" description={`${label} · calculados no backend a partir dos dados simulados`}
        actions={<>
          <Button variant="outline" loading={busy === 'csv'} disabled={!data} onClick={() => void exportAs('csv')}><Download className="h-4 w-4" />CSV</Button>
          <Button variant="outline" loading={busy === 'pdf'} disabled={!data} onClick={() => void exportAs('pdf')}><FileText className="h-4 w-4" />PDF</Button>
        </>} />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Tipo de relatório">
        {kinds.data?.items.map((k) => (
          <button key={k.kind} role="tab" aria-selected={kind === k.kind} onClick={() => setKind(k.kind)}
            className={cn('cursor-pointer rounded-lg border px-3 py-1.5 text-sm transition-colors', kind === k.kind ? 'border-primary bg-primary/15 text-fg' : 'border-line text-muted hover:bg-surface-2 hover:text-fg')}>
            {k.title.replace('Relatório de ', '').replace('Relatório ', '')}
          </button>
        ))}
      </div>
      {error ? <ErrorState error={error} onRetry={() => void refetch()} /> : isLoading || !data ? <Card><LoadingRows rows={8} /></Card> : (
        <div className="space-y-4">
          <Card>
            <CardHeader><div><CardTitle className="text-base">{data.title}</CardTitle>
              <p className="mt-0.5 text-xs text-muted">Período: {fmtDateTime(data.period.from)} → {fmtDateTime(data.period.to)} · gerado em {fmtDateTime(data.generated_at)}</p></div></CardHeader>
            <CardContent><p className="text-sm leading-relaxed">{data.summary}</p></CardContent>
          </Card>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            {data.indicators.map((i) => (
              <Card key={i.label}><CardContent className="pt-3"><p className="text-xs text-muted">{i.label}</p><p className="tabular mt-0.5 text-xl font-semibold">{i.value}</p></CardContent></Card>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader><CardTitle className="flex items-center gap-2"><TriangleAlert className="h-4 w-4 text-warn" />Principais problemas</CardTitle></CardHeader>
              <CardContent>{data.problems.length ? <ul className="space-y-1.5 text-sm">{data.problems.map((p) => <li key={p} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />{p}</li>)}</ul> : <p className="text-sm text-muted">Nenhum problema identificado pelas regras.</p>}</CardContent></Card>
            <Card><CardHeader><CardTitle className="flex items-center gap-2"><Lightbulb className="h-4 w-4 text-accent" />Recomendações</CardTitle></CardHeader>
              <CardContent><ul className="space-y-1.5 text-sm">{data.recommendations.map((p) => <li key={p} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />{p}</li>)}</ul></CardContent></Card>
          </div>
          <Card className="overflow-hidden">
            <CardHeader><CardTitle>Detalhamento</CardTitle></CardHeader>
            {data.table.rows.length === 0 ? <EmptyState title="Sem registros para detalhar" /> : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="border-y border-line text-left text-xs text-muted"><tr>{data.table.columns.map((c) => <th key={c} scope="col" className="px-4 py-2.5 font-medium">{c}</th>)}</tr></thead>
                  <tbody className="divide-y divide-line">{data.table.rows.map((r, i) => <tr key={i} className="hover:bg-surface-2/50">{r.map((c, j) => <td key={j} className={cn('px-4 py-2', j === 0 && 'font-mono text-xs text-accent')}>{c}</td>)}</tr>)}</tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  )
}
