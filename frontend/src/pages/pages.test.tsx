import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { tokenStore } from '@/lib/api'
import CopilotPage from '@/pages/CopilotPage'
import LoginPage from '@/pages/LoginPage'
import OrdersPage from '@/pages/OrdersPage'
import { adminUser, mockApi, renderApp } from '@/test/utils'

afterEach(() => { vi.unstubAllGlobals(); tokenStore.clear() })

describe('LoginPage', () => {
  it('shows validation errors without calling the API', async () => {
    const api = mockApi({})
    renderApp(<LoginPage />, { authenticated: false })
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Informe o e-mail')).toBeInTheDocument()
    expect(screen.getByText('Informe a senha')).toBeInTheDocument()
    expect(api.calls.some((c) => c.path === '/auth/login')).toBe(false)  // invalid form never reaches the API
  })

  it.each([['demo', true], ['development', true], ['production', false]])('demo credentials hint for environment=%s -> %s', async (environment, visible) => {
    mockApi({ '/health': () => ({ status: 'ok', environment }) })
    renderApp(<LoginPage />, { authenticated: false })
    await screen.findByRole('button', { name: 'Entrar' })
    if (visible) expect(await screen.findByText('opspilot-demo')).toBeInTheDocument()
    else {
      await new Promise((r) => setTimeout(r, 300)) // give the /health query time to settle
      expect(screen.queryByText('opspilot-demo')).not.toBeInTheDocument()
    }
  })

  it('stores the token on success and shows the API error on failure', async () => {
    let ok = false
    mockApi({
      '/auth/login': () => (ok
        ? { access_token: 'jwt', expires_in: 3600, user: adminUser }
        : new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Invalid email or password' } }), { status: 401 })),
    })
    renderApp(<LoginPage />, { authenticated: false })
    await userEvent.type(screen.getByLabelText('E-mail'), 'admin@opspilot.local')
    await userEvent.type(screen.getByLabelText('Senha'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
    expect(tokenStore.get()).toBeNull()

    ok = true
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await vi.waitFor(() => expect(tokenStore.get()).toBe('jwt'))
  })
})

const order = (code: string, over = {}) => ({
  id: code, code, status: 'IN_DELIVERY', situation: 'delayed', restaurant: { id: 'r', code: 'R-001', name: 'Sabor Urbano' }, customer_name: 'Ana Lopes',
  courier: null, total_amount: 42, created_at: '2026-01-01T10:00:00Z', promised_at: '2026-01-01T10:40:00Z', est_prep_minutes: 20, est_delivery_minutes: 40,
  is_delayed: true, delay_minutes: 17, delay_priority: 'HIGH', at_risk: false, risk_reasons: [], remaining_minutes: -17, ...over,
})

describe('OrdersPage', () => {
  it('lists orders, applies URL filters and refetches when a filter changes', async () => {
    const api = mockApi({
      '/restaurants': () => ({ items: [{ id: 'r', code: 'R-001', name: 'Sabor Urbano' }] }),
      '/orders': (url) => ({
        items: url.searchParams.get('status') === 'CANCELLED' ? [] : [order('ORD-1042'), order('ORD-1043', { status: 'PREPARING', situation: 'at_risk', is_delayed: false, at_risk: true })],
        total: url.searchParams.get('status') === 'CANCELLED' ? 0 : 2, page: 1, page_size: 15,
      }),
    })
    renderApp(<OrdersPage />, { route: '/pedidos?situation=delayed' })
    expect(await screen.findByText('ORD-1042')).toBeInTheDocument()
    expect(api.calls.find((c) => c.path === '/orders')).toBeDefined()
    expect((api.fn.mock.calls.find((c) => String(c[0]).includes('/orders?')) ?? [''])[0]).toContain('situation=delayed')
    expect(screen.getByText('+17 min')).toBeInTheDocument()
    expect(screen.getAllByText('sem entregador')).toHaveLength(2)

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'CANCELLED')
    expect(await screen.findByText('Nenhum pedido encontrado')).toBeInTheDocument()
  })

  it('shows an error state with retry when the API fails', async () => {
    mockApi({
      '/restaurants': () => ({ items: [] }),
      '/orders': () => new Response(JSON.stringify({ error: { code: 'internal_error', message: 'Internal server error' } }), { status: 500 }),
    })
    renderApp(<OrdersPage />)
    expect(await screen.findByText('Não foi possível carregar os dados')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tentar novamente/ })).toBeInTheDocument()
  })
})

describe('CopilotPage', () => {
  const status = { mode: 'demo', provider: 'demo', model: null, label: 'Modo demonstrativo', configuration_warning: null,
    tools: [{ name: 'get_delayed_orders', description: '', mutates: false }, { name: 'create_incident', description: '', mutates: true }], limits: {} }

  it('announces demo mode, sends a suggestion and separates data from recommendations', async () => {
    const api = mockApi({
      '/ai/status': () => status,
      '/ai/conversations': () => ({ items: [] }),
      '/ai/chat': () => ({
        conversation_id: 'c1', configuration_warning: null,
        message: {
          id: 'm1', role: 'assistant', created_at: '2026-01-01T10:00:00Z', content: '**2 pedido(s) atrasado(s)**\n- **ORD-1042** · 17 min',
          metadata: { mode: 'demo', provider: 'demo', recommendations: ['Contatar o cliente de ORD-1042.'], order_refs: ['ORD-1042'],
            tool_runs: [{ tool: 'get_delayed_orders', arguments: { limit: 15 }, status: 'SUCCESS', result: { total_delayed: 2 }, error: null, duration_ms: 12, execution_id: 'e1' }] },
        },
      }),
    })
    renderApp(<CopilotPage />)
    expect(await screen.findByText(/Modo demonstrativo/, { selector: 'b' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Quais pedidos estão atrasados?' }))

    expect(await screen.findByText(/Ferramentas utilizadas \(1\)/)).toBeInTheDocument()
    // once in the chip of the answer and once in the sidebar list of available tools
    expect(screen.getAllByText('get_delayed_orders', { selector: 'code' })).toHaveLength(2)
    expect(screen.getByText('Dados consultados')).toBeInTheDocument()
    const rec = screen.getByText(/Recomendações geradas pela IA/).closest('div')!
    expect(within(rec).getByText('Contatar o cliente de ORD-1042.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ORD-1042' })).toBeInTheDocument()
    expect(api.calls.find((c) => c.path === '/ai/chat')?.body).toMatchObject({ message: 'Quais pedidos estão atrasados?' })
  })

  it('requires explicit confirmation before an incident is created', async () => {
    const api = mockApi({
      '/ai/status': () => status,
      '/ai/conversations': () => ({ items: [] }),
      '/auth/me': () => adminUser,
      '/ai/chat': () => ({
        conversation_id: 'c1', configuration_warning: null,
        message: { id: 'm2', role: 'assistant', created_at: '2026-01-01T10:00:00Z', content: 'Preparei a ocorrência, mas ela ainda não foi criada.',
          metadata: { mode: 'demo', tool_runs: [{ tool: 'create_incident', arguments: {}, status: 'PENDING_CONFIRMATION', error: null, duration_ms: 3, execution_id: 'ex-9',
            result: { requires_confirmation: true, proposal: { type: 'DELIVERY_DELAY', priority: 'HIGH', order_code: 'ORD-1042', description: 'Cliente aguardando há 40 minutos' } } }] } },
      }),
      '/ai/executions/ex-9/confirm': () => ({ execution_id: 'ex-9', status: 'CONFIRMED', message: 'Ocorrência **OP-025** criada com sucesso (HIGH).' }),
      '/ai/conversations/c1': () => ({ id: 'c1', messages: [] }),
    })
    renderApp(<Routes><Route path="*" element={<CopilotPage />} /></Routes>)
    await userEvent.type(await screen.findByLabelText('Mensagem para o Copilot'), 'Abra uma ocorrência para ORD-1042: Cliente aguardando há 40 minutos{Enter}')
    expect(await screen.findByText(/Confirmação necessária/)).toBeInTheDocument()
    expect(api.calls.some((c) => c.path.includes('/confirm'))).toBe(false)   // nothing executed yet
    await userEvent.click(await screen.findByRole('button', { name: /Confirmar e criar/ }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.path === '/ai/executions/ex-9/confirm')?.body).toEqual({ approve: true }))
  })
})
