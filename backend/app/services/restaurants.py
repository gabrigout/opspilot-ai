"""Restaurant performance analytics."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Restaurant
from app.models.enums import ACTIVE_STATUSES, OrderStatus
from app.rules.engine import RuleConfig, restaurant_prep_alert
from app.services.orders import assess


def _prep_minutes(o: Order) -> float | None:
    return (o.ready_at - o.created_at).total_seconds() / 60 if o.ready_at else None


def _is_late(o: Order, now: datetime, cfg: RuleConfig) -> bool:
    if o.status == OrderStatus.DELIVERED:
        return bool(o.delivered_at and o.delivered_at > o.promised_at)
    return o.status in ACTIVE_STATUSES and assess(o, now, cfg).is_delayed


def restaurant_stats(db: Session, now: datetime, cfg: RuleConfig, hours: int = 24) -> dict:
    since = now - timedelta(hours=hours)
    restaurants = list(db.scalars(select(Restaurant).order_by(Restaurant.code)))
    orders = list(db.scalars(select(Order).where(Order.created_at >= since)))
    by_rest: dict = {r.id: [] for r in restaurants}
    for o in orders:
        by_rest[o.restaurant_id].append(o)
    all_prep = [p for o in orders if (p := _prep_minutes(o)) is not None]
    op_avg = round(sum(all_prep) / len(all_prep), 1) if all_prep else None

    rows = []
    for r in restaurants:
        os_ = by_rest[r.id]
        preps = [p for o in os_ if (p := _prep_minutes(o)) is not None]
        observed = round(sum(preps) / len(preps), 1) if preps else None
        cancelled = sum(1 for o in os_ if o.status == OrderStatus.CANCELLED)
        alert_pct = restaurant_prep_alert(observed, op_avg, len(preps), cfg)
        rows.append({
            "id": str(r.id), "code": r.code, "name": r.name, "category": r.category, "address": r.address,
            "status": r.status.value, "rating": r.rating, "baseline_prep_minutes": r.avg_prep_minutes,
            "avg_prep_minutes": observed,
            "orders": len(os_), "cancelled": cancelled,
            "cancellation_rate": round(cancelled / len(os_) * 100, 1) if os_ else 0.0,
            "delayed_orders": sum(1 for o in os_ if _is_late(o, now, cfg)),
            "vs_operation_avg_pct": round((observed / op_avg - 1) * 100, 1) if observed and op_avg else None,
            "prep_alert": alert_pct is not None, "prep_alert_pct": alert_pct,
        })
    return {"period_hours": hours, "operation_avg_prep_minutes": op_avg, "restaurants": rows}
