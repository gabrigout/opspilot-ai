import { Fragment, type ReactNode } from 'react'

/** Minimal, XSS-safe renderer for the subset the agent emits: **bold**, *italic*, `code`, lists and paragraphs. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const rx = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = rx.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) out.push(<strong key={i++}>{tok.slice(2, -2)}</strong>)
    else if (tok.startsWith('`')) out.push(<code key={i++} className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[12px] text-accent">{tok.slice(1, -1)}</code>)
    else out.push(<em key={i++}>{tok.slice(1, -1)}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let list: { ordered: boolean; items: { text: string; sub: string[] }[] } | null = null
  const flush = () => {
    if (!list) return
    const L = list
    const Tag = L.ordered ? 'ol' : 'ul'
    blocks.push(
      <Tag key={blocks.length} className={L.ordered ? 'my-1 list-decimal space-y-1 pl-5' : undefined}>
        {L.items.map((it, i) => (
          <li key={i}>{inline(it.text)}{it.sub.length > 0 && <ul className="mt-0.5 text-muted">{it.sub.map((s, j) => <li key={j}>{inline(s)}</li>)}</ul>}</li>
        ))}
      </Tag>,
    )
    list = null
  }
  for (const raw of lines) {
    const sub = /^\s{2,}[-*]\s+(.*)$/.exec(raw)
    const bullet = /^[-*]\s+(.*)$/.exec(raw)
    const num = /^\d+\.\s+(.*)$/.exec(raw)
    if (sub && list) { list.items[list.items.length - 1].sub.push(sub[1]); continue }
    if (bullet || num) {
      const ordered = !!num
      if (list && list.ordered !== ordered) flush()
      list ??= { ordered, items: [] }
      list.items.push({ text: (bullet ?? num)![1], sub: [] })
      continue
    }
    flush()
    if (raw.trim()) blocks.push(<p key={blocks.length} className="my-1.5">{inline(raw)}</p>)
  }
  flush()
  return <div className="prose-ops text-sm leading-relaxed">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>
}
