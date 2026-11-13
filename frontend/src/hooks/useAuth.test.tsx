import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '@/hooks/useAuth'
import { tokenStore } from '@/lib/api'
import { adminUser, mockApi, renderApp } from '@/test/utils'

function Probe() {
  const { user, loading } = useAuth()
  return <p>{loading ? 'loading' : user ? `hello ${user.full_name}` : 'anonymous'}</p>
}

afterEach(() => { vi.unstubAllGlobals(); tokenStore.clear() })

describe('session restore', () => {
  it('restores the user from a stored token', async () => {
    mockApi({ '/auth/me': () => adminUser })
    renderApp(<Probe />)
    expect(await screen.findByText('hello Admin Demo')).toBeInTheDocument()
  })

  it('drops the token on 401 (expired/invalid session)', async () => {
    mockApi({ '/auth/me': () => new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Invalid or expired token' } }), { status: 401 }) })
    renderApp(<Probe />)
    expect(await screen.findByText('anonymous')).toBeInTheDocument()
    expect(tokenStore.get()).toBeNull()
  })

  it('keeps the token and retries when the backend is temporarily unreachable', async () => {
    let calls = 0
    vi.stubGlobal('fetch', vi.fn(async () => {
      calls += 1
      if (calls === 1) throw new TypeError('connection reset')
      return new Response(JSON.stringify(adminUser), { status: 200 })
    }))
    renderApp(<Probe />)
    expect(await screen.findByText('hello Admin Demo', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(tokenStore.get()).toBe('test-token')
    expect(calls).toBe(2)
  })
})
