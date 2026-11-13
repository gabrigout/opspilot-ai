import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AuthProvider } from '@/hooks/useAuth'
import { PeriodProvider } from '@/hooks/usePeriod'
import { tokenStore } from '@/lib/api'

type Route = (url: URL, init?: RequestInit) => unknown | Promise<unknown>

/** Routes fetch() calls by pathname (without /api/v1). Unknown paths fail the test loudly. */
export function mockApi(routes: Record<string, Route>, status = 200) {
  const calls: { path: string; method: string; body?: unknown }[] = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const path = url.pathname.replace('/api/v1', '')
    const handler = routes[path]
    calls.push({ path, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (!handler) return new Response(JSON.stringify({ error: { code: 'not_found', message: `unmocked ${path}` } }), { status: 404 })
    const out = await handler(url, init)
    if (out instanceof Response) return out
    return new Response(JSON.stringify(out), { status, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fn)
  return { calls, fn }
}

export function renderApp(ui: ReactElement, { route = '/', authenticated = true } = {}) {
  if (authenticated) tokenStore.set('test-token')
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider><PeriodProvider>{ui}</PeriodProvider></AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export const adminUser = { id: '1', email: 'admin@opspilot.local', full_name: 'Admin Demo', role: 'ADMIN' as const }
