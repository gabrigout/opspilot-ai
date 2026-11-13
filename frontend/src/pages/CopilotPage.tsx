import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, ChevronDown, Database, Lightbulb, Loader2, MessageSquarePlus, SendHorizontal, ShieldCheck, Wrench, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Markdown } from '@/components/Markdown'
import { OrderDrawer } from '@/components/OrderDrawer'
import { ErrorState, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { errorMessage, get, post } from '@/lib/api'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AiStatus, ChatMessage, ToolRun } from '@/types/api'

const SUGGESTIONS = [
  'Quais pedidos estão atrasados?',
  'Quais pedidos correm risco de atraso?',
  'Como está a operação hoje?',
  'Quais restaurantes apresentam problemas?',
  'Quantos entregadores estão disponíveis?',
  'Gere um relatório operacional',
]

interface ChatResponse { conversation_id: string; message: ChatMessage; configuration_warning: string | null }
interface Conversation { id: string; title: string; created_at: string }

function ToolChip({ run }: { run: ToolRun }) {
  const tone = run.status === 'SUCCESS' ? 'success' : run.status === 'PENDING_CONFIRMATION' ? 'warn' : run.status === 'ERROR' ? 'danger' : 'accent'
  return (
    <details className="group rounded-lg border border-line bg-bg/50 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-1.5">
        <Wrench className="h-3.5 w-3.5 text-accent" aria-hidden />
        <code className="font-mono text-[12px]">{run.tool}</code>
        <Badge tone={tone}>{run.status === 'SUCCESS' ? 'ok' : run.status === 'PENDING_CONFIRMATION' ? 'aguarda confirmação' : run.status.toLowerCase()}</Badge>
        <span className="tabular ml-auto text-muted">{run.duration_ms} ms</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-2 border-t border-line p-2.5">
        <div><p className="mb-0.5 text-[10px] uppercase tracking-wide text-muted">Argumentos validados</p>
          <pre className="overflow-x-auto rounded bg-surface-2/60 p-2 font-mono text-[11px]">{JSON.stringify(run.arguments, null, 2)}</pre></div>
        <div><p className="mb-0.5 text-[10px] uppercase tracking-wide text-muted">Dados consultados (resposta da ferramenta)</p>
          <pre className="max-h-48 overflow-auto rounded bg-surface-2/60 p-2 font-mono text-[11px]">{run.error ?? JSON.stringify(run.result, null, 2)}</pre></div>
      </div>
    </details>
  )
}

function PendingAction({ run, onDone }: { run: ToolRun; onDone: (executionId: string, approve: boolean) => Promise<void> }) {
  const { canWrite } = useAuth()
  const [busy, setBusy] = useState<'yes' | 'no' | null>(null)
  const p = (run.result?.proposal ?? run.arguments) as Record<string, string>
  if (run.status !== 'PENDING_CONFIRMATION') {
    return run.status === 'CONFIRMED' || run.status === 'REJECTED' ? (
      <p className="text-xs text-muted">{run.status === 'CONFIRMED' ? '✓ Ação confirmada e executada.' : '✕ Ação cancelada.'}</p>
    ) : null
  }
  const act = async (approve: boolean) => { setBusy(approve ? 'yes' : 'no'); try { await onDone(run.execution_id!, approve) } finally { setBusy(null) } }
  return (
    <div className="rounded-lg border border-warn/40 bg-warn/5 p-3" role="group" aria-label="Confirmação de ação">
      <p className="flex items-center gap-1.5 text-sm font-medium"><ShieldCheck className="h-4 w-4 text-warn" />Confirmação necessária: criar ocorrência</p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted">
        <dt>Tipo</dt><dd className="text-fg">{p.type}</dd><dt>Prioridade</dt><dd className="text-fg">{p.priority}</dd>
        {p.order_code && (<><dt>Pedido</dt><dd className="text-fg">{p.order_code}</dd></>)}<dt>Descrição</dt><dd className="text-fg">{p.description}</dd>
      </dl>
      {canWrite ? (
        <div className="mt-2.5 flex gap-2">
          <Button size="sm" loading={busy === 'yes'} disabled={!!busy} onClick={() => void act(true)}><Check className="h-3.5 w-3.5" />Confirmar e criar</Button>
          <Button size="sm" variant="ghost" loading={busy === 'no'} disabled={!!busy} onClick={() => void act(false)}><X className="h-3.5 w-3.5" />Cancelar</Button>
        </div>
      ) : <p className="mt-2 text-xs text-warn">Seu perfil é somente leitura.</p>}
    </div>
  )
}

function AssistantMessage({ m, onOpenOrder, onConfirm }: { m: ChatMessage; onOpenOrder: (c: string) => void; onConfirm: (id: string, approve: boolean) => Promise<void> }) {
  const meta = m.metadata
  const runs = meta.tool_runs ?? []
  return (
    <div className="flex gap-3">
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/20 text-[#a5a8ff]"><Bot className="h-4 w-4" aria-hidden /></div>
      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold">OpsPilot AI Copilot</span>
          {meta.mode === 'demo' && <Badge tone="warn">Modo demonstrativo · sem LLM externo</Badge>}
          {meta.mode === 'llm' && <Badge tone="success">{meta.provider} · {meta.model}</Badge>}
          {meta.blocked && <Badge tone="danger">Pedido bloqueado</Badge>}
          {meta.error && <Badge tone="danger">{meta.error}</Badge>}
        </div>
        {runs.length > 0 && (
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted"><Wrench className="h-3 w-3" />Ferramentas utilizadas ({runs.length})</p>
            {runs.map((r, i) => <ToolChip key={r.execution_id ?? i} run={r} />)}
          </div>
        )}
        <div className="rounded-xl border border-line bg-surface/90 p-3.5">
          <p className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted"><Database className="h-3 w-3" />{runs.length ? 'Dados consultados' : 'Resposta'}</p>
          <Markdown text={m.content} />
        </div>
        {runs.filter((r) => r.tool === 'create_incident').map((r, i) => <PendingAction key={r.execution_id ?? i} run={r} onDone={onConfirm} />)}
        {!!meta.recommendations?.length && (
          <div className="rounded-xl border border-primary/40 bg-primary/10 p-3.5">
            <p className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-[#a5a8ff]"><Lightbulb className="h-3 w-3" />Recomendações geradas pela IA (não são dados consultados)</p>
            <Markdown text={meta.recommendations.map((r) => `- ${r}`).join('\n')} />
          </div>
        )}
        {!!meta.order_refs?.length && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-muted">Pedidos citados:</span>
            {meta.order_refs.slice(0, 12).map((c) => <button key={c} onClick={() => onOpenOrder(c)} className="cursor-pointer rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-accent hover:underline">{c}</button>)}
          </div>
        )}
      </div>
    </div>
  )
}

export default function CopilotPage() {
  const qc = useQueryClient()
  const [convId, setConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [order, setOrder] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const status = useQuery({ queryKey: ['ai-status'], queryFn: () => get<AiStatus>('/ai/status') })
  const convs = useQuery({ queryKey: ['conversations'], queryFn: () => get<{ items: Conversation[] }>('/ai/conversations') })

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, pending])

  const load = async (id: string) => {
    try {
      const c = await get<{ messages: ChatMessage[] }>(`/ai/conversations/${id}`)
      setConvId(id); setMessages(c.messages)
    } catch (e) { toast.error(errorMessage(e)) }
  }

  const send = async (text: string) => {
    const msg = text.trim()
    if (!msg || pending) return
    setInput(''); setPending(true)
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: 'user', content: msg, created_at: new Date().toISOString(), metadata: {} }])
    try {
      const r = await post<ChatResponse>('/ai/chat', { message: msg, conversation_id: convId ?? undefined })
      setConvId(r.conversation_id)
      setMessages((m) => [...m, r.message])
      void qc.invalidateQueries({ queryKey: ['conversations'] })
    } catch (e) {
      setMessages((m) => [...m, { id: `err-${Date.now()}`, role: 'assistant', content: errorMessage(e), created_at: new Date().toISOString(), metadata: { error: 'request_failed', mode: status.data?.mode } }])
    } finally { setPending(false) }
  }

  const confirm = async (executionId: string, approve: boolean) => {
    try {
      const r = await post<{ status: string; message: string }>(`/ai/executions/${executionId}/confirm`, { approve })
      toast[approve && r.status === 'CONFIRMED' ? 'success' : 'info'](r.message.replace(/\*\*/g, ''))
      if (convId) await load(convId)
      void qc.invalidateQueries()
    } catch (e) { toast.error(errorMessage(e)) }
  }

  const demo = status.data?.mode === 'demo'
  return (
    <>
      <PageHeader title="AI Copilot" description="Pergunte sobre a operação. O agente consulta o backend por ferramentas controladas e explica o que encontrou."
        actions={<Button variant="outline" onClick={() => { setConvId(null); setMessages([]) }}><MessageSquarePlus className="h-4 w-4" />Nova conversa</Button>} />
      {status.error && <ErrorState error={status.error} />}
      {status.data && (
        <div className={cn('mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-4 py-2.5 text-sm', demo ? 'border-warn/40 bg-warn/5' : 'border-success/40 bg-success/5')}>
          <span className={cn('h-2 w-2 rounded-full', demo ? 'bg-warn' : 'bg-success')} aria-hidden />
          <b>{demo ? 'Modo demonstrativo' : `Conectado: ${status.data.provider} (${status.data.model})`}</b>
          <span className="text-muted">{demo ? 'Sem LLM externo: perguntas interpretadas por padrões; as ferramentas e os dados são reais.' : 'As respostas são geradas por um LLM usando as ferramentas do backend.'}</span>
          {status.data.configuration_warning && <span className="text-warn">{status.data.configuration_warning}</span>}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
        <section className="flex h-[calc(100vh-17rem)] min-h-[28rem] flex-col rounded-xl border border-line bg-surface/60" aria-label="Conversa com o Copilot">
          <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-5" aria-live="polite">
            {messages.length === 0 && (
              <div className="mx-auto max-w-xl py-8 text-center">
                <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-primary/20 text-[#a5a8ff]"><Bot className="h-6 w-6" /></div>
                <h2 className="text-base font-semibold">Como posso ajudar na operação?</h2>
                <p className="mt-1 text-sm text-muted">Comece por uma sugestão ou pergunte sobre um pedido (ex.: “mostre o pedido ORD-1042”).</p>
                <div className="mt-5 grid gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => <button key={s} onClick={() => void send(s)} className="cursor-pointer rounded-lg border border-line bg-bg/40 px-3 py-2.5 text-left text-sm hover:border-primary/60 hover:bg-surface-2">{s}</button>)}
                </div>
              </div>
            )}
            {messages.map((m) => m.role === 'user' ? (
              <div key={m.id} className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-white">{m.content}</div></div>
            ) : <AssistantMessage key={m.id} m={m} onOpenOrder={setOrder} onConfirm={confirm} />)}
            {pending && (
              <div className="flex items-center gap-3 text-sm text-muted" role="status"><div className="grid h-8 w-8 place-items-center rounded-lg bg-primary/20"><Loader2 className="h-4 w-4 animate-spin text-[#a5a8ff]" /></div>Consultando ferramentas do backend…</div>
            )}
            <div ref={endRef} />
          </div>
          <form className="flex gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); void send(input) }}>
            <label htmlFor="chat-input" className="sr-only">Mensagem para o Copilot</label>
            <input id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} autoComplete="off" placeholder="Pergunte sobre pedidos, entregadores, restaurantes…"
              className="h-10 flex-1 rounded-lg border border-line bg-bg/60 px-3 text-sm placeholder:text-muted/70 focus-visible:border-primary" />
            <Button type="submit" size="lg" disabled={!input.trim() || pending} aria-label="Enviar"><SendHorizontal className="h-4 w-4" /><span className="hidden sm:inline">Enviar</span></Button>
          </form>
        </section>

        <aside className="space-y-4">
          <div className="rounded-xl border border-line bg-surface/60 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Conversas</h3>
            {convs.data?.items.length ? (
              <ul className="max-h-60 space-y-1 overflow-y-auto">
                {convs.data.items.map((c) => (
                  <li key={c.id}><button onClick={() => void load(c.id)} className={cn('w-full cursor-pointer rounded-md px-2 py-1.5 text-left text-xs hover:bg-surface-2', convId === c.id && 'bg-surface-2')}>
                    <span className="block truncate">{c.title}</span><span className="text-[10px] text-muted">{timeAgo(c.created_at)}</span></button></li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted">Nenhuma conversa ainda.</p>}
          </div>
          <div className="rounded-xl border border-line bg-surface/60 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Ferramentas do agente ({status.data?.tools.length ?? 0})</h3>
            <ul className="space-y-1.5">
              {status.data?.tools.map((t) => <li key={t.name} title={t.description} className="flex items-center gap-1.5 text-xs"><Wrench className="h-3 w-3 shrink-0 text-accent" /><code className="truncate font-mono text-[11px]">{t.name}</code>{t.mutates && <Badge tone="warn" className="ml-auto">confirma</Badge>}</li>)}
            </ul>
          </div>
        </aside>
      </div>
      <OrderDrawer code={order} onClose={() => setOrder(null)} />
    </>
  )
}
