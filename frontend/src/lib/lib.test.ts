import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, errorMessage, tokenStore } from '@/lib/api'
import { fmtMin, fmtMoney, INCIDENT_TYPE_LABEL, label, timeAgo } from '@/lib/format'

afterEach(() => { vi.unstubAllGlobals(); tokenStore.clear() })

describe('format helpers', () => {
  it('formats minutes and null values', () => {
    expect(fmtMin(12.4)).toBe('12 min')
    expect(fmtMin(null)).toBe('—')
  })
  it('formats BRL currency', () => {
    expect(fmtMoney(1234.5).replace(/\s/g, ' ')).toBe('R$ 1.234,50')
  })
  it('describes relative time', () => {
    const now = Date.parse('2026-01-01T12:00:00Z')
    expect(timeAgo('2026-01-01T11:59:40Z', now)).toBe('agora')
    expect(timeAgo('2026-01-01T11:30:00Z', now)).toBe('30 min atrás')
    expect(timeAgo('2026-01-01T09:00:00Z', now)).toBe('3 h atrás')
    expect(timeAgo('2025-12-30T12:00:00Z', now)).toBe('2 d atrás')
  })
  it('labels known and unknown keys', () => {
    expect(label(INCIDENT_TYPE_LABEL, 'DELIVERY_DELAY')).toBe('Atraso na entrega')
    expect(label(INCIDENT_TYPE_LABEL, 'UNKNOWN')).toBe('UNKNOWN')
    expect(label(INCIDENT_TYPE_LABEL, null)).toBe('—')
  })
})

describe('api client', () => {
  it('sends the bearer token and parses JSON', async () => {
    tokenStore.set('abc')
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await api('/ping')).toEqual({ ok: true })
    const headers = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer abc')
  })

  it('maps standard error envelopes to ApiError and readable validation messages', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'validation_error', message: 'Invalid request', details: [{ field: 'description', message: 'too short' }] } }), { status: 422 })))
    const err = (await api('/x').catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(errorMessage(err)).toBe('description: too short')
  })

  it('clears the token and notifies on 401', async () => {
    tokenStore.set('expired')
    const listener = vi.fn()
    window.addEventListener('opspilot:unauthorized', listener)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Invalid or expired token' } }), { status: 401 })))
    await expect(api('/x')).rejects.toMatchObject({ status: 401 })
    expect(tokenStore.get()).toBeNull()
    expect(listener).toHaveBeenCalled()
    window.removeEventListener('opspilot:unauthorized', listener)
  })

  it('reports a friendly message when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    await expect(api('/x')).rejects.toMatchObject({ code: 'network_error' })
  })
})
