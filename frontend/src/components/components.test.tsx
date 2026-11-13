import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PriorityBadge, SituationBadge, StatusBadge } from '@/components/badges'
import { IncidentFormDialog } from '@/components/IncidentForm'
import { Markdown } from '@/components/Markdown'
import { adminUser, mockApi, renderApp } from '@/test/utils'
import { tokenStore } from '@/lib/api'

afterEach(() => { vi.unstubAllGlobals(); tokenStore.clear() })

describe('Markdown', () => {
  it('renders bold text, code and lists', () => {
    renderApp(<Markdown text={'**7 pedidos** atrasados\n- ORD-1 · `CRITICAL`\n- ORD-2'} />, { authenticated: false })
    expect(screen.getByText('7 pedidos').tagName).toBe('STRONG')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('CRITICAL').tagName).toBe('CODE')
  })

  it('never injects HTML coming from the agent', () => {
    const { container } = renderApp(<Markdown text={'<img src=x onerror=alert(1)> <script>alert(1)</script>'} />, { authenticated: false })
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.textContent).toContain('<img src=x')
  })
})

describe('badges', () => {
  it('translate domain values into Portuguese labels', () => {
    renderApp(<><StatusBadge status="WAITING_COURIER" /><SituationBadge situation="delayed" /><PriorityBadge priority="CRITICAL" /></>, { authenticated: false })
    expect(screen.getByText('Aguardando entregador')).toBeInTheDocument()
    expect(screen.getByText('Atrasado')).toBeInTheDocument()
    expect(screen.getByText('Crítica')).toBeInTheDocument()
  })
})

describe('IncidentFormDialog', () => {
  it('validates the description before submitting', async () => {
    const api = mockApi({ '/auth/me': () => adminUser })
    renderApp(<IncidentFormDialog open onOpenChange={() => {}} orderRef="ORD-1042" />)
    await userEvent.type(screen.getByLabelText('Descrição'), 'abc')
    await userEvent.click(screen.getByRole('button', { name: 'Criar ocorrência' }))
    expect(await screen.findByText(/mín\. 5 caracteres/)).toBeInTheDocument()
    expect(api.calls.some((c) => c.path === '/incidents')).toBe(false)
  })

  it('posts the validated payload and closes on success', async () => {
    const onOpenChange = vi.fn()
    const api = mockApi({
      '/auth/me': () => adminUser,
      '/incidents': () => ({ code: 'OP-099' }),
    })
    renderApp(<IncidentFormDialog open onOpenChange={onOpenChange} orderRef="ORD-1042" />)
    await userEvent.selectOptions(screen.getByLabelText('Prioridade'), 'HIGH')
    await userEvent.type(screen.getByLabelText('Descrição'), 'Cliente aguardando há 40 minutos')
    await userEvent.click(screen.getByRole('button', { name: 'Criar ocorrência' }))
    await vi.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    const post = api.calls.find((c) => c.path === '/incidents' && c.method === 'POST')
    expect(post?.body).toMatchObject({ type: 'DELIVERY_DELAY', priority: 'HIGH', order_ref: 'ORD-1042', description: 'Cliente aguardando há 40 minutos' })
  })
})
