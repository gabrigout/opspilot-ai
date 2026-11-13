const dtf = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
const tf = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' })
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

export const fmtDateTime = (iso?: string | null) => (iso ? dtf.format(new Date(iso)) : '—')
export const fmtTime = (iso?: string | null) => (iso ? tf.format(new Date(iso)) : '—')
export const fmtMoney = (n: number) => brl.format(n)
export const fmtMin = (n?: number | null) => (n == null ? '—' : `${Math.round(n)} min`)

export function timeAgo(iso: string, now = Date.now()): string {
  const m = Math.round((now - new Date(iso).getTime()) / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m} min atrás`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h} h atrás` : `${Math.floor(h / 24)} d atrás`
}

export const STATUS_LABEL: Record<string, string> = {
  RECEIVED: 'Recebido', CONFIRMED: 'Confirmado', PREPARING: 'Em preparo', READY_FOR_PICKUP: 'Pronto p/ retirada',
  WAITING_COURIER: 'Aguardando entregador', IN_DELIVERY: 'Em entrega', DELIVERED: 'Entregue', CANCELLED: 'Cancelado',
  AVAILABLE: 'Disponível', ASSIGNED: 'Atribuído', PICKING_UP: 'Retirando', DELIVERING: 'Entregando', OFFLINE: 'Offline',
  OPEN: 'Aberta', INVESTIGATING: 'Investigando', WAITING_ACTION: 'Aguardando ação', RESOLVED: 'Resolvida', CLOSED: 'Fechada',
  BUSY: 'Ocupado', PAUSED: 'Pausado', CLOSED_R: 'Fechado',
}
export const INCIDENT_TYPE_LABEL: Record<string, string> = {
  DELIVERY_DELAY: 'Atraso na entrega', SLOW_PREPARATION: 'Preparo demorado', COURIER_SHORTAGE: 'Falta de entregador',
  ORDER_CANCELLED: 'Pedido cancelado', COURIER_ISSUE: 'Problema com entregador', CUSTOMER_COMPLAINT: 'Reclamação de cliente',
  ADDRESS_ISSUE: 'Problema de endereço', ORDER_NOT_FOUND: 'Pedido não localizado',
}
export const PRIORITY_LABEL: Record<string, string> = { LOW: 'Baixa', MEDIUM: 'Média', HIGH: 'Alta', CRITICAL: 'Crítica' }
export const SITUATION_LABEL: Record<string, string> = {
  delayed: 'Atrasado', at_risk: 'Em risco', on_track: 'No prazo', delivered: 'Entregue', cancelled: 'Cancelado',
}
export const label = (map: Record<string, string>, k?: string | null) => (k ? map[k] ?? k : '—')
