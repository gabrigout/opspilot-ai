"""Operational KPIs and chart series, always computed from the database."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Courier, Incident, OperationalEvent, Order
from app.models.enums import (
    OPEN_INCIDENT_STATUSES,
    CourierStatus,
    OrderStatus,
)
from app.rules.engine import RuleConfig
from app.services.alerts import compute_alerts
from app.services.orders import active_orders, iso
from app.services.restaurants import restaurant_stats


def _bucket(dt: datetime, daily: bool) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0, **({"hour": 0} if daily else {}))


def _bucket_range(since: datetime, now: datetime, daily: bool) -> list[datetime]:
    cur, step = _bucket(since, daily), timedelta(days=1) if daily else timedelta(hours=1)
    out = []
    while cur <= now:
        out.append(cur)
        cur += step
    return out


def kpis(db: Session, now: datetime, cfg: RuleConfig, hours: int = 24) -> dict:
    since = now - timedelta(hours=hours)
    window = list(db.scalars(select(Order).where(Order.created_at >= since)))
    delivered = [o for o in window if o.status == OrderStatus.DELIVERED and o.delivered_at]
    durations = [(o.delivered_at - o.created_at).total_seconds() / 60 for o in delivered]
    active = active_orders(db, now, cfg)
    return {
        "period_hours": hours,
        "total_orders": len(window),
        "in_progress": len(active),
        "delivered": len(delivered),
        "delayed": sum(1 for _, a in active if a.is_delayed),
        "at_risk": sum(1 for _, a in active if a.at_risk),
        "cancelled": sum(1 for o in window if o.status == OrderStatus.CANCELLED),
        "waiting_courier": sum(1 for o, _ in active if o.status in (OrderStatus.READY_FOR_PICKUP, OrderStatus.WAITING_COURIER) and not o.courier_id),
        "avg_delivery_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "available_couriers": db.scalar(select(func.count()).select_from(Courier).where(Courier.status == CourierStatus.AVAILABLE)) or 0,
        "total_couriers": db.scalar(select(func.count()).select_from(Courier)) or 0,
        "open_incidents": db.scalar(select(func.count()).select_from(Incident).where(Incident.status.in_(OPEN_INCIDENT_STATUSES))) or 0,
    }


def charts(db: Session, now: datetime, cfg: RuleConfig, hours: int = 24) -> dict:
    since = now - timedelta(hours=hours)
    daily = hours > 72
    window = list(db.scalars(select(Order).where(Order.created_at >= since)))
    buckets = _bucket_range(since, now, daily)

    volume = Counter(_bucket(o.created_at, daily) for o in window)
    cancels = Counter(_bucket(o.cancelled_at, daily) for o in window if o.cancelled_at)
    dur = defaultdict(list)
    for o in window:
        if o.status == OrderStatus.DELIVERED and o.delivered_at:
            dur[_bucket(o.created_at, daily)].append((o.delivered_at - o.created_at).total_seconds() / 60)
    inc_types = Counter(
        t.value for t in db.scalars(select(Incident.type).where(Incident.created_at >= since))
    )
    rest = restaurant_stats(db, now, cfg, hours)["restaurants"]
    rest = sorted((r for r in rest if r["orders"]), key=lambda r: -r["orders"])[:8]
    return {
        "period_hours": hours,
        "granularity": "day" if daily else "hour",
        "order_volume": [{"bucket": iso(b), "orders": volume.get(b, 0)} for b in buckets],
        "orders_by_status": [{"status": s, "count": c} for s, c in Counter(o.status.value for o in window).most_common()],
        "avg_delivery_time": [
            {"bucket": iso(b), "minutes": round(sum(dur[b]) / len(dur[b]), 1) if dur.get(b) else None} for b in buckets
        ],
        "incident_distribution": [{"type": t, "count": c} for t, c in inc_types.most_common()],
        "restaurant_performance": [
            {"name": r["name"], "orders": r["orders"], "avg_prep_minutes": r["avg_prep_minutes"],
             "cancellation_rate": r["cancellation_rate"], "delayed_orders": r["delayed_orders"]}
            for r in rest
        ],
        "cancellations": [{"bucket": iso(b), "cancelled": cancels.get(b, 0)} for b in buckets],
    }


def activity_feed(db: Session, now: datetime, limit: int = 15) -> list[dict]:
    rows = db.scalars(
        select(OperationalEvent).where(OperationalEvent.created_at <= now)
        .order_by(OperationalEvent.created_at.desc()).limit(limit)
    )
    return [
        {"id": str(e.id), "type": e.event_type, "severity": e.severity.value, "message": e.message,
         "entity_type": e.entity_type, "entity_id": e.entity_id, "actor": e.actor, "created_at": iso(e.created_at)}
        for e in rows
    ]


def overview(db: Session, now: datetime, cfg: RuleConfig, hours: int = 24) -> dict:
    return {
        "generated_at": iso(now),
        "simulated_data": True,
        "kpis": kpis(db, now, cfg, hours),
        "charts": charts(db, now, cfg, hours),
        "alerts": compute_alerts(db, now, cfg),
        "activity": activity_feed(db, now),
    }
