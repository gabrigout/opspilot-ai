const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''
const PREFIX = `${BASE}/api/v1`
const TOKEN_KEY = 'opspilot_token'

export const tokenStore = {
  get: () => {
    try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
  },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t) } catch { /* storage unavailable */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ } },
}

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

type Query = Record<string, string | number | boolean | undefined | null>

function qs(params?: Query) {
  if (!params) return ''
  const s = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') s.set(k, String(v))
  })
  const out = s.toString()
  return out ? `?${out}` : ''
}

async function raw(path: string, init: RequestInit & { params?: Query } = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let res: Response
  try {
    res = await fetch(`${PREFIX}${path}${qs(init.params)}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'network_error', 'Não foi possível conectar à API. Verifique se o backend está em execução.')
  }
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; details?: unknown } } = {}
    try { body = await res.json() } catch { /* non-JSON error */ }
    if (res.status === 401 && token) {
      tokenStore.clear()
      window.dispatchEvent(new Event('opspilot:unauthorized'))
    }
    throw new ApiError(res.status, body.error?.code ?? 'error', body.error?.message ?? `Erro ${res.status}`, body.error?.details)
  }
  return res
}

export async function api<T>(path: string, init: RequestInit & { params?: Query } = {}): Promise<T> {
  const res = await raw(path, init)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const get = <T,>(path: string, params?: Query) => api<T>(path, { params })
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

export async function download(path: string, params: Query, fallbackName: string) {
  const res = await raw(path, { params })
  const blob = await res.blob()
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'validation_error' && Array.isArray(e.details)) {
      return (e.details as { field: string; message: string }[]).map((d) => `${d.field}: ${d.message}`).join('; ')
    }
    return e.message
  }
  return e instanceof Error ? e.message : 'Erro inesperado'
}
