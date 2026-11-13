"""Order queries, serialization and the status state machine."""
import re
import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.errors import ConflictError, InvalidTransitionError, NotFoundError
from app.models import Courier, Order, OrderEvent, Restaurant
from app.models.enums import (
    ACTIVE_STATUSES,
    CourierStatus,
    OrderStatus,
    Severity,
)
from app.rules.engine import (
    ALLOWED_TRANSITIONS,
    PRE_DELIVERY,
    OrderAssessment,
    OrderSnapshot,
    RuleConfig,
    assess_order,
    is_valid_transition,
)
from app.services import events

SITUATIONS = ("delayed", "at_risk", "on_track")


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def snapshot(o: Order) -> OrderSnapshot:
    return OrderSnapshot(
        status=o.status, created_at=o.created_at, promised_at=o.promised_at,
        est_prep_minutes=o.est_prep_minutes, has_courier=o.courier_id is not None, ready_at=o.ready_at,
    )


def assess(o: Order, now: datetime, cfg: RuleConfig) -> OrderAssessment:
    return assess_order(snapshot(o), now, cfg)


def situation_of(a: OrderAssessment, o: Order) -> str:
    if o.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        return o.status.value.lower()
    return "delayed" if a.is_delayed else "at_risk" if a.at_risk else "on_track"


def order_summary(o: Order, now: datetime, cfg: RuleConfig) -> dict:
    a = assess(o, now, cfg)
    return {
        "id": str(o.id),
        "code": o.code,
        "status": o.status.value,
        "situation": situation_of(a, o),
        "restaurant": {"id": str(o.restaurant_id), "code": o.restaurant.code, "name": o.restaurant.name},
        "customer_name": o.customer.name,
        "courier": {"id": str(o.courier_id), "code": o.courier.code, "name": o.courier.name} if o.courier else None,
        "total_amount": float(o.total_amount),
        "created_at": iso(o.created_at),
        "promised_at": iso(o.promised_at),
        "est_prep_minutes": o.est_prep_minutes,
        "est_delivery_minutes": o.est_delivery_minutes,
        "is_delayed": a.is_delayed,
        "delay_minutes": a.delay_minutes,
        "delay_priority": a.priority.value if a.priority else None,
        "at_risk": a.at_risk,
        "risk_reasons": list(a.risk_reasons),
        "remaining_minutes": a.remaining_minutes,
    }


def order_detail(o: Order, now: datetime, cfg: RuleConfig) -> dict:
    d = order_summary(o, now, cfg)
    d.update(
        customer={"name": o.customer.name, "phone": o.customer.phone, "address": o.customer.address},
        items=[
            {"name": i.name, "quantity": i.quantity, "unit_price": float(i.unit_price)} for i in o.items
        ],
        ready_at=iso(o.ready_at), picked_up_at=iso(o.picked_up_at), delivered_at=iso(o.delivered_at),
        cancelled_at=iso(o.cancelled_at), cancel_reason=o.cancel_reason,
        allowed_transitions=[s.value for s in ALLOWED_TRANSITIONS[o.status]],
        history=[event_out(e) for e in o.events],
    )
    return d


def event_out(e: OrderEvent) -> dict:
    return {
        "id": str(e.id), "event_type": e.event_type, "from_status": e.from_status, "to_status": e.to_status,
        "message": e.message, "actor": e.actor, "created_at": iso(e.created_at),
    }


_EAGER = (joinedload(Order.restaurant), joinedload(Order.customer), joinedload(Order.courier))


def find_order(db: Session, ident: str, detail: bool = False) -> Order:
    """Find by UUID or by code ('ORD-1042', '1042' or '#1042')."""
    opts = list(_EAGER) + ([selectinload(Order.items), selectinload(Order.events)] if detail else [])
    stmt = select(Order).options(*opts)
    ident = ident.strip()
    try:
        stmt = stmt.where(Order.id == uuid.UUID(ident))
    except ValueError:
        m = re.search(r"(\d+)\s*$", ident)
        code = f"ORD-{m.group(1)}" if m else ident.upper()
        stmt = stmt.where(Order.code == code)
    order = db.scalars(stmt).first()
    if not order:
        raise NotFoundError(f"Order '{ident}' not found")
    return order


def find_restaurant(db: Session, ident: str) -> Restaurant:
    ident = ident.strip()
    try:
        r = db.get(Restaurant, uuid.UUID(ident))
    except ValueError:
        r = db.scalars(select(Restaurant).where(func.lower(Restaurant.code) == ident.lower())).first()
        if not r:
            r = db.scalars(select(Restaurant).where(func.lower(Restaurant.name).contains(ident.lower()))).first()
    if not r:
        raise NotFoundError(f"Restaurant '{ident}' not found")
    return r


def query_orders(
    db: Session,
    now: datetime,
    cfg: RuleConfig,
    *,
    status: OrderStatus | None = None,
    restaurant: str | None = None,
    q: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    situation: str | None = None,
    courier_id: uuid.UUID | None = None,
    no_courier: bool = False,
) -> list[tuple[Order, OrderAssessment]]:
    stmt = select(Order).options(*_EAGER).order_by(Order.created_at.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if restaurant:
        rid = find_restaurant(db, restaurant).id
        stmt = stmt.where(Order.restaurant_id == rid)
    if q:
        like = f"%{q.strip().lstrip('#')}%"
        stmt = stmt.where(or_(Order.code.ilike(like), Order.code.ilike(f"%{q.strip().lstrip('#')}")))
    if since:
        stmt = stmt.where(Order.created_at >= since)
    if until:
        stmt = stmt.where(Order.created_at <= until)
    if courier_id:
        stmt = stmt.where(Order.courier_id == courier_id)
    if no_courier:
        stmt = stmt.where(Order.courier_id.is_(None))
    rows = [(o, assess(o, now, cfg)) for o in db.scalars(stmt).unique()]
    if situation:
        if situation not in SITUATIONS:
            raise NotFoundError(f"Unknown situation '{situation}'")
        rows = [(o, a) for o, a in rows if situation_of(a, o) == situation]
    return rows


def active_orders(db: Session, now: datetime, cfg: RuleConfig) -> list[tuple[Order, OrderAssessment]]:
    stmt = select(Order).options(*_EAGER).where(Order.status.in_(ACTIVE_STATUSES))
    return [(o, assess(o, now, cfg)) for o in db.scalars(stmt).unique()]


# --------------------------------------------------------------------- state machine
def _release_courier(db: Session, courier: Courier, now: datetime, delivered: Order | None = None) -> None:
    others = db.scalar(
        select(func.count()).select_from(Order).where(
            Order.courier_id == courier.id, Order.status.in_(ACTIVE_STATUSES),
            Order.id != (delivered.id if delivered else uuid.uuid4()),
        )
    )
    if delivered and delivered.status == OrderStatus.DELIVERED and delivered.picked_up_at:
        minutes = (delivered.delivered_at - delivered.picked_up_at).total_seconds() / 60
        total = courier.avg_delivery_minutes * courier.total_deliveries + minutes
        courier.total_deliveries += 1
        courier.avg_delivery_minutes = round(total / courier.total_deliveries, 1)
    if not others and courier.status != CourierStatus.OFFLINE:
        courier.status = CourierStatus.AVAILABLE
    courier.updated_at = now


def change_status(
    db: Session, order: Order, target: OrderStatus, now: datetime, actor: str = "system",
    reason: str | None = None,
) -> Order:
    current = order.status
    if not is_valid_transition(current, target):
        allowed = ", ".join(s.value for s in ALLOWED_TRANSITIONS[current]) or "none (terminal)"
        raise InvalidTransitionError(
            f"Cannot move order {order.code} from {current.value} to {target.value}. Allowed: {allowed}",
            {"current": current.value, "target": target.value, "allowed": [s.value for s in ALLOWED_TRANSITIONS[current]]},
        )
    if target == OrderStatus.IN_DELIVERY and not order.courier_id:
        raise InvalidTransitionError(f"Order {order.code} needs a courier before going IN_DELIVERY")

    order.status = target
    order.updated_at = now
    message = f"Status alterado de {current.value} para {target.value}"
    severity = Severity.INFO
    if target == OrderStatus.READY_FOR_PICKUP:
        order.ready_at = now
    elif target == OrderStatus.IN_DELIVERY:
        order.picked_up_at = now
        if order.courier:
            order.courier.status = CourierStatus.DELIVERING
            order.courier.updated_at = now
    elif target == OrderStatus.DELIVERED:
        order.delivered_at = now
        if order.courier:
            _release_courier(db, order.courier, now, order)
    elif target == OrderStatus.CANCELLED:
        order.cancelled_at = now
        order.cancel_reason = reason or "Cancelado pelo operador"
        message += f": {order.cancel_reason}"
        severity = Severity.WARNING
        if order.courier:
            _release_courier(db, order.courier, now)

    db.add(OrderEvent(order=order, event_type="STATUS_CHANGED", from_status=current.value,
                      to_status=target.value, message=message, actor=actor, created_at=now))
    events.log_event(db, now, "ORDER_STATUS", f"Pedido {order.code}: {message.lower()}", severity,
                     "order", str(order.id), {"code": order.code, "to": target.value}, actor)
    return order


def assign_courier(db: Session, order: Order, courier: Courier, now: datetime, actor: str) -> Order:
    """Explicit (human or rule-driven) assignment. Never called implicitly."""
    if order.status not in PRE_DELIVERY:
        raise ConflictError(f"Order {order.code} is {order.status.value}; a courier can only be assigned before pickup")
    if courier.status != CourierStatus.AVAILABLE:
        raise ConflictError(f"Courier {courier.code} is {courier.status.value}, not AVAILABLE")
    if order.courier and order.courier_id != courier.id:
        _release_courier(db, order.courier, now)
    order.courier = courier
    order.courier_id = courier.id  # keep the FK attribute in sync before flush (rules read courier_id)
    order.updated_at = now
    courier.status = CourierStatus.ASSIGNED
    courier.updated_at = now
    db.add(OrderEvent(order=order, event_type="COURIER_ASSIGNED", message=f"Entregador {courier.code} ({courier.name}) atribuído",
                      actor=actor, created_at=now))
    events.log_event(db, now, "COURIER_ASSIGNED", f"Entregador {courier.code} atribuído ao pedido {order.code}",
                     Severity.INFO, "order", str(order.id), {"courier": courier.code}, actor)
    return order
