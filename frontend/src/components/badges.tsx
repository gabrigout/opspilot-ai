import { Badge, type Tone } from '@/components/ui/badge'
import { INCIDENT_TYPE_LABEL, label, PRIORITY_LABEL, SITUATION_LABEL, STATUS_LABEL } from '@/lib/format'

const STATUS_TONE: Record<string, Tone> = {
  RECEIVED: 'neutral', CONFIRMED: 'neutral', PREPARING: 'primary', READY_FOR_PICKUP: 'accent', WAITING_COURIER: 'warn',
  IN_DELIVERY: 'accent', DELIVERED: 'success', CANCELLED: 'danger',
  AVAILABLE: 'success', ASSIGNED: 'primary', PICKING_UP: 'accent', DELIVERING: 'accent', OFFLINE: 'neutral',
  OPEN: 'danger', INVESTIGATING: 'warn', WAITING_ACTION: 'warn', RESOLVED: 'success', CLOSED: 'neutral',
  BUSY: 'warn', PAUSED: 'neutral',
}
const PRIORITY_TONE: Record<string, Tone> = { LOW: 'neutral', MEDIUM: 'primary', HIGH: 'warn', CRITICAL: 'danger' }
const SITUATION_TONE: Record<string, Tone> = { delayed: 'danger', at_risk: 'warn', on_track: 'success', delivered: 'neutral', cancelled: 'neutral' }

export const StatusBadge = ({ status }: { status: string }) => <Badge tone={STATUS_TONE[status] ?? 'neutral'}>{label(STATUS_LABEL, status)}</Badge>
export const PriorityBadge = ({ priority }: { priority?: string | null }) =>
  priority ? <Badge tone={PRIORITY_TONE[priority] ?? 'neutral'}>{label(PRIORITY_LABEL, priority)}</Badge> : <span className="text-muted">—</span>
export const SituationBadge = ({ situation }: { situation: string }) =>
  <Badge tone={SITUATION_TONE[situation] ?? 'neutral'}>{label(SITUATION_LABEL, situation)}</Badge>
export const IncidentTypeText = ({ type }: { type: string }) => <>{label(INCIDENT_TYPE_LABEL, type)}</>
