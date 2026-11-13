"""Courier queries, status updates and the recommendation algorithm."""
import math
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Courier, Order
from app.models.enums import ACTIVE_STATUSES, CourierStatus, Severity
from app.rules.engine import RuleConfig
from app.services import events
from app.services.orders import iso

AVG_SPEED_KMH = 22.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def active_counts(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(Order.courier_id, func.count()).where(
            Order.courier_id.is_not(None), Order.status.in_(ACTIVE_STATUSES)
        ).group_by(Order.courier_id)
    )
    return {cid: n for cid, n in rows}


def courier_out(c: Courier, active: int, now: datetime | None = None) -> dict:
    return {
        "id": str(c.id), "code": c.code, "name": c.name, "status": c.status.value,
        "location": {"lat": round(c.lat, 5), "lng": round(c.lng, 5)},
        "active_orders": active, "total_deliveries": c.total_deliveries,
        "avg_delivery_minutes": c.avg_delivery_minutes, "updated_at": iso(c.updated_at),
        "idle_minutes": round((now - c.updated_at).total_seconds() / 60, 1)
        if now and c.status == CourierStatus.AVAILABLE else None,
    }


def list_couriers(db: Session, now: datetime, status: CourierStatus | None = None) -> list[dict]:
    stmt = select(Courier).order_by(Courier.code)
    if status:
        stmt = stmt.where(Courier.status == status)
    counts = active_counts(db)
    return [courier_out(c, counts.get(c.id, 0), now) for c in db.scalars(stmt)]


def get_courier(db: Session, ident: str) -> Courier:
    try:
        c = db.get(Courier, uuid.UUID(ident))
    except ValueError:
        c = db.scalars(select(Courier).where(func.upper(Courier.code) == ident.strip().upper())).first()
    if not c:
        raise NotFoundError(f"Courier '{ident}' not found")
    return c


def set_status(db: Session, courier: Courier, status: CourierStatus, now: datetime, actor: str) -> Courier:
    active = active_counts(db).get(courier.id, 0)
    if status in (CourierStatus.AVAILABLE, CourierStatus.OFFLINE) and active:
        raise ConflictError(f"Courier {courier.code} has {active} active order(s); finish or reassign them first")
    if status in (CourierStatus.ASSIGNED, CourierStatus.PICKING_UP, CourierStatus.DELIVERING) and not active:
        raise ConflictError(f"Courier {courier.code} has no active order; status {status.value} requires one")
    previous, courier.status, courier.updated_at = courier.status, status, now
    events.log_event(db, now, "COURIER_STATUS", f"Entregador {courier.code} mudou de {previous.value} para {status.value}",
                     Severity.INFO, "courier", str(courier.id), None, actor)
    return courier


def recommend(db: Session, order: Order, now: datetime, cfg: RuleConfig, limit: int = 5) -> dict:
    """Rank AVAILABLE couriers for an order. Never assigns anything.

    Score (0-100):
      distance to restaurant ..... up to 50 pts (linear, 0 at max_courier_distance_km)
      workload (active orders) ... 25 / 10 / 0 pts for 0 / 1 / 2+ orders
      idle time .................. up to 15 pts (1 pt per idle minute, capped at 15)
      fairness ................... up to 10 pts favouring couriers with fewer total deliveries
    Couriers farther than max_courier_distance_km are excluded (compatibility rule).
    """
    r = order.restaurant
    counts = active_counts(db)
    ranked, excluded = [], 0
    for c in db.scalars(select(Courier).where(Courier.status == CourierStatus.AVAILABLE)):
        dist = haversine_km(c.lat, c.lng, r.lat, r.lng)
        if dist > cfg.max_courier_distance_km:
            excluded += 1
            continue
        load = counts.get(c.id, 0)
        idle = max(0.0, (now - c.updated_at).total_seconds() / 60)
        s_dist = 50 * (1 - dist / cfg.max_courier_distance_km)
        s_load = 25 if load == 0 else 10 if load == 1 else 0
        s_idle = min(15.0, idle)
        s_fair = 10 * (1 - min(c.total_deliveries, 60) / 60)
        score = round(s_dist + s_load + s_idle + s_fair, 1)
        eta = round(dist / AVG_SPEED_KMH * 60 + 2, 1)
        ranked.append({
            "courier": courier_out(c, load, now), "score": score, "distance_km": round(dist, 2),
            "eta_to_restaurant_minutes": eta,
            "breakdown": {"distance": round(s_dist, 1), "workload": s_load, "idle_time": round(s_idle, 1), "fairness": round(s_fair, 1)},
            "reasons": [
                f"{dist:.1f} km do restaurante (~{eta:.0f} min)",
                f"{load} pedido(s) ativo(s)",
                f"ocioso há {idle:.0f} min",
            ],
        })
    ranked.sort(key=lambda x: (-x["score"], x["distance_km"]))
    return {
        "order_code": order.code, "restaurant": r.name, "auto_assigned": False,
        "candidates": ranked[:limit], "total_eligible": len(ranked), "excluded_too_far": excluded,
        "note": "Recomendação apenas; a atribuição exige aprovação humana (POST /orders/{id}/assign).",
    }
