"""Incident management with full change history."""
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, NotFoundError
from app.models import Incident, OperationalEvent
from app.models.enums import (
    OPEN_INCIDENT_STATUSES,
    PRIORITY_RANK,
    IncidentStatus,
    IncidentType,
    Priority,
    Severity,
)
from app.services import events
from app.services.orders import find_order, iso

TYPE_TITLES = {
    IncidentType.DELIVERY_DELAY: "Atraso na entrega",
    IncidentType.SLOW_PREPARATION: "Restaurante demorando na preparação",
    IncidentType.COURIER_SHORTAGE: "Falta de entregador",
    IncidentType.ORDER_CANCELLED: "Pedido cancelado",
    IncidentType.COURIER_ISSUE: "Problema com entregador",
    IncidentType.CUSTOMER_COMPLAINT: "Reclamação de cliente",
    IncidentType.ADDRESS_ISSUE: "Problema de endereço",
    IncidentType.ORDER_NOT_FOUND: "Pedido não localizado",
}


def incident_out(i: Incident) -> dict:
    return {
        "id": str(i.id), "code": i.code, "type": i.type.value, "priority": i.priority.value,
        "status": i.status.value, "title": i.title, "description": i.description,
        "assignee": i.assignee, "resolution": i.resolution, "created_by": i.created_by,
        "order": {"id": str(i.order_id), "code": i.order.code} if i.order else None,
        "restaurant": {"id": str(i.restaurant_id), "name": i.restaurant.name} if i.restaurant else None,
        "created_at": iso(i.created_at), "updated_at": iso(i.updated_at), "resolved_at": iso(i.resolved_at),
    }


def _next_code(db: Session) -> str:
    n = db.scalar(select(func.count()).select_from(Incident)) or 0
    code = f"OP-{n + 1:03d}"
    while db.scalar(select(func.count()).select_from(Incident).where(Incident.code == code)):
        n += 1
        code = f"OP-{n + 1:03d}"
    return code


def get_incident(db: Session, ident: str) -> Incident:
    stmt = select(Incident).options(joinedload(Incident.order), joinedload(Incident.restaurant))
    try:
        stmt = stmt.where(Incident.id == uuid.UUID(ident))
    except ValueError:
        stmt = stmt.where(Incident.code == ident.strip().upper())
    inc = db.scalars(stmt).first()
    if not inc:
        raise NotFoundError(f"Incident '{ident}' not found")
    return inc


def create_incident(
    db: Session, now: datetime, *, type: IncidentType, description: str, priority: Priority,
    order_ref: str | None = None, title: str | None = None, assignee: str | None = None, actor: str = "system",
) -> Incident:
    order = find_order(db, order_ref) if order_ref else None
    inc = Incident(
        code=_next_code(db), type=type, priority=priority, status=IncidentStatus.OPEN,
        title=title or TYPE_TITLES[type], description=description, assignee=assignee, created_by=actor,
        order_id=order.id if order else None, restaurant_id=order.restaurant_id if order else None,
        created_at=now, updated_at=now,
    )
    inc.order, inc.restaurant = order, order.restaurant if order else None
    db.add(inc)
    db.flush()
    sev = Severity.CRITICAL if priority == Priority.CRITICAL else Severity.WARNING if priority == Priority.HIGH else Severity.INFO
    events.log_event(db, now, "INCIDENT_CREATED",
                     f"Ocorrência {inc.code} aberta ({inc.title}{' – pedido ' + order.code if order else ''})",
                     sev, "incident", str(inc.id), {"code": inc.code, "priority": priority.value}, actor)
    return inc


def update_incident(
    db: Session, inc: Incident, now: datetime, actor: str, *, status: IncidentStatus | None = None,
    priority: Priority | None = None, assignee: str | None = None, resolution: str | None = None,
    description: str | None = None,
) -> Incident:
    if inc.status == IncidentStatus.CLOSED:
        raise ConflictError(f"Incident {inc.code} is CLOSED and cannot be changed")
    new_status = status or inc.status
    if new_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and not (resolution or inc.resolution):
        raise ConflictError("A resolution text is required to resolve or close an incident")
    if new_status == IncidentStatus.CLOSED and inc.status != IncidentStatus.RESOLVED:
        raise ConflictError("Only RESOLVED incidents can be CLOSED")

    changes: dict[str, dict] = {}

    def apply(field: str, new):
        old = getattr(inc, field)
        if new is not None and new != old:
            changes[field] = {"from": getattr(old, "value", old), "to": getattr(new, "value", new)}
            setattr(inc, field, new)

    apply("status", status)
    apply("priority", priority)
    apply("assignee", assignee)
    apply("resolution", resolution)
    apply("description", description)
    if not changes:
        return inc
    if inc.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and not inc.resolved_at:
        inc.resolved_at = now
    inc.updated_at = now
    summary = ", ".join(f"{k}: {v['from']} → {v['to']}" for k, v in changes.items() if k != "resolution" and k != "description")
    if "resolution" in changes:
        summary = (summary + "; " if summary else "") + "resolução registrada"
    if "description" in changes:
        summary = (summary + "; " if summary else "") + "descrição atualizada"
    events.log_event(db, now, "INCIDENT_UPDATED", f"Ocorrência {inc.code} atualizada ({summary})",
                     Severity.INFO, "incident", str(inc.id), {"changes": changes}, actor)
    return inc


def list_incidents(
    db: Session, *, status: IncidentStatus | None = None, priority: Priority | None = None,
    open_only: bool = False, order_ref: str | None = None,
) -> list[Incident]:
    stmt = select(Incident).options(joinedload(Incident.order), joinedload(Incident.restaurant))
    if status:
        stmt = stmt.where(Incident.status == status)
    if open_only:
        stmt = stmt.where(Incident.status.in_(OPEN_INCIDENT_STATUSES))
    if priority:
        stmt = stmt.where(Incident.priority == priority)
    if order_ref:
        stmt = stmt.where(Incident.order_id == find_order(db, order_ref).id)
    rows = list(db.scalars(stmt))
    rows.sort(key=lambda i: (-PRIORITY_RANK[i.priority], i.created_at))
    return rows


def incident_history(db: Session, inc: Incident) -> list[dict]:
    stmt = (select(OperationalEvent).where(OperationalEvent.entity_type == "incident",
                                           OperationalEvent.entity_id == str(inc.id))
            .order_by(OperationalEvent.created_at))
    return [
        {"id": str(e.id), "event_type": e.event_type, "message": e.message, "actor": e.actor,
         "changes": (e.payload or {}).get("changes"), "created_at": iso(e.created_at)}
        for e in db.scalars(stmt)
    ]
