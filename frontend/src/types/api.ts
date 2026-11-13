export type OrderStatus = 'RECEIVED' | 'CONFIRMED' | 'PREPARING' | 'READY_FOR_PICKUP' | 'WAITING_COURIER' | 'IN_DELIVERY' | 'DELIVERED' | 'CANCELLED'
export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type IncidentStatus = 'OPEN' | 'INVESTIGATING' | 'WAITING_ACTION' | 'RESOLVED' | 'CLOSED'
export type CourierStatus = 'AVAILABLE' | 'ASSIGNED' | 'PICKING_UP' | 'DELIVERING' | 'OFFLINE'
export type Role = 'ADMIN' | 'OPERATOR' | 'VIEWER'

export interface User { id: string; email: string; full_name: string; role: Role }
export interface Token { access_token: string; expires_in: number; user: User }

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface OrderSummary {
  id: string; code: string; status: OrderStatus; situation: string
  restaurant: { id: string; code: string; name: string }
  customer_name: string
  courier: { id: string; code: string; name: string } | null
  total_amount: number; created_at: string; promised_at: string
  est_prep_minutes: number; est_delivery_minutes: number
  is_delayed: boolean; delay_minutes: number; delay_priority: Priority | null
  at_risk: boolean; risk_reasons: string[]; remaining_minutes: number | null
}
export interface OrderEvent { id: string; event_type: string; from_status: string | null; to_status: string | null; message: string; actor: string; created_at: string }
export interface OrderDetail extends OrderSummary {
  customer: { name: string; phone: string; address: string }
  items: { name: string; quantity: number; unit_price: number }[]
  ready_at: string | null; picked_up_at: string | null; delivered_at: string | null; cancelled_at: string | null; cancel_reason: string | null
  allowed_transitions: OrderStatus[]
  history: OrderEvent[]
}

export interface Courier {
  id: string; code: string; name: string; status: CourierStatus
  location: { lat: number; lng: number }; active_orders: number; total_deliveries: number
  avg_delivery_minutes: number; updated_at: string; idle_minutes: number | null
}
export interface CourierDetail extends Courier { recent_orders: OrderSummary[] }
export interface Recommendation {
  order_code: string; restaurant: string; auto_assigned: boolean; total_eligible: number; excluded_too_far: number; note: string
  candidates: { courier: Courier; score: number; distance_km: number; eta_to_restaurant_minutes: number; reasons: string[]; breakdown: Record<string, number> }[]
}

export interface Restaurant {
  id: string; code: string; name: string; category: string; address: string; status: string; rating: number
  baseline_prep_minutes: number; avg_prep_minutes: number | null; orders: number; cancelled: number; cancellation_rate: number
  delayed_orders: number; vs_operation_avg_pct: number | null; prep_alert: boolean; prep_alert_pct: number | null
}
export interface RestaurantDetail extends Restaurant { operation_avg_prep_minutes: number | null; period_hours: number; recent_orders: OrderSummary[] }

export interface Incident {
  id: string; code: string; type: string; priority: Priority; status: IncidentStatus; title: string; description: string
  assignee: string | null; resolution: string | null; created_by: string
  order: { id: string; code: string } | null; restaurant: { id: string; name: string } | null
  created_at: string; updated_at: string; resolved_at: string | null
}
export interface IncidentHistory { id: string; event_type: string; message: string; actor: string; created_at: string; changes?: Record<string, { from: unknown; to: unknown }> }
export interface IncidentDetail extends Incident { history: IncidentHistory[] }

export interface Kpis {
  period_hours: number; total_orders: number; in_progress: number; delivered: number; delayed: number; at_risk: number
  cancelled: number; waiting_courier: number; avg_delivery_minutes: number | null; available_couriers: number
  total_couriers: number; open_incidents: number
}
export interface Alert { id: string; rule: string; level: 'INFO' | 'WARNING' | 'CRITICAL'; title: string; message: string; orders: string[] }
export interface Activity { id: string; type: string; severity: 'INFO' | 'WARNING' | 'CRITICAL'; message: string; entity_type: string | null; entity_id: string | null; actor: string; created_at: string }
export interface Charts {
  granularity: 'hour' | 'day'
  order_volume: { bucket: string; orders: number }[]
  orders_by_status: { status: string; count: number }[]
  avg_delivery_time: { bucket: string; minutes: number | null }[]
  incident_distribution: { type: string; count: number }[]
  restaurant_performance: { name: string; orders: number; avg_prep_minutes: number | null; cancellation_rate: number; delayed_orders: number }[]
  cancellations: { bucket: string; cancelled: number }[]
}
export interface Overview { generated_at: string; kpis: Kpis; charts: Charts; alerts: Alert[]; activity: Activity[] }

export interface Report {
  kind: string; title: string; generated_at: string; period: { hours: number; from: string; to: string }
  indicators: { label: string; value: string | number }[]; summary: string; problems: string[]; recommendations: string[]
  table: { columns: string[]; rows: (string | number)[][] }
}

export interface ToolRun { tool: string; arguments: Record<string, unknown>; status: string; result: Record<string, unknown> | null; error: string | null; duration_ms: number; execution_id?: string }
export interface ChatMessage {
  id: string; role: 'user' | 'assistant'; content: string; created_at: string
  metadata: { mode?: string; provider?: string; model?: string | null; tool_runs?: ToolRun[]; recommendations?: string[]; order_refs?: string[]; blocked?: boolean; error?: string }
}
export interface AiStatus {
  mode: 'demo' | 'llm'; provider: string; model: string | null; label: string; configuration_warning: string | null
  tools: { name: string; description: string; mutates: boolean }[]
  limits: { max_iterations: number; timeout_seconds: number; messages_per_minute: number; tool_calls_per_turn: number }
}
export interface SimStatus { simulated: boolean; now: string; offset_minutes: number; last_action: string | null; active_orders: number; available_couriers: number; offline_couriers: number; notice: string }
