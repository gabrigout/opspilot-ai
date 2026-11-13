"""User-controlled operational simulator.

Nothing runs in the background: the simulated clock only moves when the user calls
`advance`. Every action writes to the real tables, so dashboards, reports and the AI
agent all see the effects. All data is fictitious.
"""
import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import Courier, Customer, Incident, Order, OrderEvent, OrderItem, Restaurant
from app.models.enums import (
    ACTIVE_STATUSES,
    OPEN_INCIDENT_STATUSES,
    CourierStatus,
    IncidentType,
    OrderStatus,
    RestaurantStatus,
    Severity,
)
from app.rules.engine import RuleConfig
from app.services import clock, couriers, events, incidents
from app.services import orders as order_svc
from app.services.seed import CENTER, DISHES, STREETS, _name


def status(db: Session) -> dict:
    st = clock.get_state(db)
    now = clock.now(db)
    return {
        "simulated": True,
        "now": now.isoformat(),
        "offset_minutes": st.offset_minutes,
        "last_action": st.last_action,
        "active_orders": db.scalar(select(func.count()).select_from(Order).where(Order.status.in_(ACTIVE_STATUSES))),
        "available_couriers": db.scalar(select(func.count()).select_from(Courier).where(Courier.status == CourierStatus.AVAILABLE)),
        "offline_couriers": db.scalar(select(func.count()).select_from(Courier).where(Courier.status == CourierStatus.OFFLINE)),
        "notice": "Todos os dados são fictícios e gerados por este simulador.",
    }


def _record(db: Session, text: str, now: datetime) -> None:
    st = clock.get_state(db)
    st.last_action, st.updated_at = text, now


def _auto_assign(db: Session, order: Order, now: datetime, cfg: RuleConfig, actor: str) -> bool:
    """Explicit simulator rule: take the top-ranked recommendation. Only used when auto_assign=True."""
    rec = couriers.recommend(db, order, now, cfg, limit=1)
    if not rec["candidates"]:
        return False
    courier = couriers.get_courier(db, rec["candidates"][0]["courier"]["id"])
    order_svc.assign_courier(db, order, courier, now, actor)
    return True


def advance(db: Session, minutes: float, cfg: RuleConfig, auto_assign: bool = True) -> dict:
    if not 0 < minutes <= 240:
        raise ConflictError("minutes must be between 0 and 240")
    st = clock.get_state(db)
    old_now = clock.now(db)
    st.offset_minutes += minutes
    now = old_now + timedelta(minutes=minutes)
    changes = {"status_changes": 0, "assignments": 0, "newly_delayed": 0}
    actor = "simulation"

    active = list(db.scalars(select(Order).where(Order.status.in_(ACTIVE_STATUSES)).order_by(Order.created_at)))
    for o in active:
        progressed = True
        while progressed:
            progressed = False
            c = o.created_at
            if o.status == OrderStatus.RECEIVED and now >= c + timedelta(minutes=2):
                order_svc.change_status(db, o, OrderStatus.CONFIRMED, c + timedelta(minutes=2), actor); progressed = True
            elif o.status == OrderStatus.CONFIRMED and now >= c + timedelta(minutes=4):
                order_svc.change_status(db, o, OrderStatus.PREPARING, c + timedelta(minutes=4), actor); progressed = True
            elif o.status == OrderStatus.PREPARING and now >= c + timedelta(minutes=o.sim_prep_minutes + 2):
                order_svc.change_status(db, o, OrderStatus.READY_FOR_PICKUP, c + timedelta(minutes=o.sim_prep_minutes + 2), actor); progressed = True
            elif o.status == OrderStatus.READY_FOR_PICKUP:
                if not o.courier_id and now >= o.ready_at + timedelta(minutes=1):
                    order_svc.change_status(db, o, OrderStatus.WAITING_COURIER, o.ready_at + timedelta(minutes=1), actor); progressed = True
                elif o.courier_id and now >= o.ready_at + timedelta(minutes=3):
                    when = max(o.ready_at + timedelta(minutes=3), o.updated_at)
                    order_svc.change_status(db, o, OrderStatus.IN_DELIVERY, min(when, now), actor); progressed = True
                else:
                    break
            elif o.status == OrderStatus.WAITING_COURIER:
                if not o.courier_id and auto_assign and _auto_assign(db, o, now, cfg, "simulation:auto-assign"):
                    changes["assignments"] += 1
                    progressed = True
                    continue
                if o.courier_id and now >= o.ready_at + timedelta(minutes=3):
                    when = max(o.ready_at + timedelta(minutes=3), o.updated_at)
                    order_svc.change_status(db, o, OrderStatus.IN_DELIVERY, min(when, now), actor); progressed = True
                else:
                    break
            elif o.status == OrderStatus.IN_DELIVERY and now >= o.picked_up_at + timedelta(minutes=o.sim_travel_minutes):
                order_svc.change_status(db, o, OrderStatus.DELIVERED, o.picked_up_at + timedelta(minutes=o.sim_travel_minutes), actor)
                changes["status_changes"] += 1
            else:
                break
            if progressed:
                changes["status_changes"] += 1
        if o.status in (OrderStatus.READY_FOR_PICKUP, OrderStatus.WAITING_COURIER, OrderStatus.RECEIVED, OrderStatus.CONFIRMED, OrderStatus.PREPARING):
            if o.courier and o.courier.status == CourierStatus.ASSIGNED and o.status in (OrderStatus.READY_FOR_PICKUP, OrderStatus.WAITING_COURIER):
                o.courier.status = CourierStatus.PICKING_UP
        if o.status in ACTIVE_STATUSES and old_now < o.promised_at <= now:
            changes["newly_delayed"] += 1
            events.log_event(db, o.promised_at, "ORDER_DELAYED", f"Pedido {o.code} entrou em situação de atraso",
                             Severity.WARNING, "order", str(o.id), {"code": o.code}, actor)
    _record(db, f"Relógio avançado em {minutes:g} min", now)
    db.commit()
    return {"now": now.isoformat(), "advanced_minutes": minutes, **changes}


def _next_number(db: Session) -> int:
    codes = db.scalars(select(Order.code)).all()
    return max([int(c.split("-")[1]) for c in codes if c.startswith("ORD-")] + [1000]) + 1


def _new_order(db: Session, now: datetime, rng: random.Random, rest: Restaurant, n: int) -> Order:
    cust = Customer(name=_name(rng), phone=f"+55 11 9{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
                    address=f"{rng.choice(STREETS)}, {rng.randint(10, 999)}",
                    lat=CENTER[0] + rng.uniform(-0.045, 0.045), lng=CENTER[1] + rng.uniform(-0.045, 0.045))
    est_prep = int(rest.avg_prep_minutes + rng.randint(-2, 3))
    travel = rng.randint(12, 24)
    est_total = est_prep + travel + 8
    o = Order(
        code=f"ORD-{n}", restaurant=rest, customer=cust, status=OrderStatus.RECEIVED, est_prep_minutes=est_prep,
        est_delivery_minutes=est_total, created_at=now, promised_at=now + timedelta(minutes=est_total), updated_at=now,
        sim_prep_minutes=round(max(4, est_prep * rest.delay_factor + rng.uniform(-1, 2)), 1),
        sim_travel_minutes=round(travel + rng.uniform(-2, 4), 1), total_amount=0,
    )
    total = 0.0
    for name, price in rng.sample(DISHES, rng.randint(1, 3)):
        q = rng.randint(1, 2)
        o.items.append(OrderItem(name=name, quantity=q, unit_price=price))
        total += q * price
    o.total_amount = round(total, 2)
    o.events.append(OrderEvent(event_type="CREATED", to_status="RECEIVED", message="Pedido recebido (simulação)",
                               actor="simulation", created_at=now))
    db.add(o)
    db.flush()
    return o


def spawn_orders(db: Session, count: int, restaurant: str | None = None) -> dict:
    now = clock.now(db)
    rng = random.Random()
    pool = [r for r in db.scalars(select(Restaurant)) if r.status in (RestaurantStatus.OPEN, RestaurantStatus.BUSY)]
    if restaurant:
        pool = [order_svc.find_restaurant(db, restaurant)]
    start = _next_number(db)
    created = [_new_order(db, now, rng, rng.choice(pool), start + i).code for i in range(count)]
    events.log_event(db, now, "SIM_ORDERS", f"Simulação: {count} novo(s) pedido(s) gerado(s)", Severity.INFO, actor="simulation")
    _record(db, f"{count} pedidos gerados", now)
    db.commit()
    return {"created": count, "codes": created}


def demand_spike(db: Session, count: int = 15) -> dict:
    res = spawn_orders(db, count)
    now = clock.now(db)
    events.log_event(db, now, "SIM_DEMAND_SPIKE", f"Simulação: pico de demanda com {count} pedidos", Severity.WARNING, actor="simulation")
    _record(db, f"Pico de demanda ({count} pedidos)", now)
    db.commit()
    return res


def reduce_couriers(db: Session, count: int) -> dict:
    now = clock.now(db)
    free = list(db.scalars(select(Courier).where(Courier.status == CourierStatus.AVAILABLE).order_by(Courier.code).limit(count)))
    for c in free:
        c.status, c.updated_at = CourierStatus.OFFLINE, now
    events.log_event(db, now, "SIM_COURIERS_OFFLINE", f"Simulação: {len(free)} entregador(es) ficaram offline", Severity.WARNING, actor="simulation")
    _record(db, f"{len(free)} entregadores offline", now)
    db.commit()
    return {"set_offline": [c.code for c in free]}


def restore_couriers(db: Session) -> dict:
    now = clock.now(db)
    off = list(db.scalars(select(Courier).where(Courier.status == CourierStatus.OFFLINE)))
    for c in off:
        c.status, c.updated_at = CourierStatus.AVAILABLE, now
    events.log_event(db, now, "SIM_COURIERS_ONLINE", f"Simulação: {len(off)} entregador(es) voltaram a ficar disponíveis", Severity.INFO, actor="simulation")
    _record(db, f"{len(off)} entregadores online", now)
    db.commit()
    return {"set_available": [c.code for c in off]}


def restaurant_delay(db: Session, restaurant: str, factor: float) -> dict:
    now = clock.now(db)
    r = order_svc.find_restaurant(db, restaurant)
    r.delay_factor = factor
    r.status = RestaurantStatus.BUSY if factor >= 1.3 else RestaurantStatus.OPEN
    affected = 0
    for o in db.scalars(select(Order).where(Order.restaurant_id == r.id, Order.status.in_(
            (OrderStatus.RECEIVED, OrderStatus.CONFIRMED, OrderStatus.PREPARING)))):
        o.sim_prep_minutes = round(o.est_prep_minutes * factor, 1)
        affected += 1
    events.log_event(db, now, "SIM_RESTAURANT_DELAY",
                     f"Simulação: {r.name} com fator de preparo x{factor:g} ({affected} pedidos afetados)",
                     Severity.WARNING if factor > 1 else Severity.INFO, "restaurant", str(r.id), actor="simulation")
    _record(db, f"{r.name}: preparo x{factor:g}", now)
    db.commit()
    return {"restaurant": r.name, "delay_factor": factor, "affected_orders": affected}


def cancel_orders(db: Session, count: int) -> dict:
    now = clock.now(db)
    rng = random.Random()
    cands = list(db.scalars(select(Order).where(Order.status.in_(
        (OrderStatus.RECEIVED, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP, OrderStatus.WAITING_COURIER)))))
    rng.shuffle(cands)
    done = []
    for o in cands[:count]:
        order_svc.change_status(db, o, OrderStatus.CANCELLED, now, "simulation", "Cancelamento simulado")
        done.append(o.code)
    _record(db, f"{len(done)} cancelamentos simulados", now)
    db.commit()
    return {"cancelled": done}


def generate_incidents(db: Session, cfg: RuleConfig) -> dict:
    """Open an incident for each delayed order that has none open yet."""
    now = clock.now(db)
    created = []
    for o, a in order_svc.active_orders(db, now, cfg):
        if not a.is_delayed:
            continue
        has_open = db.scalar(select(func.count()).select_from(Incident).where(
            Incident.order_id == o.id, Incident.status.in_(OPEN_INCIDENT_STATUSES)))
        if has_open:
            continue
        inc = incidents.create_incident(
            db, now, type=IncidentType.DELIVERY_DELAY, priority=a.priority,
            description=f"Pedido {o.code} está {a.delay_minutes:.0f} min atrasado (regra de atraso).",
            order_ref=str(o.id), actor="simulation")
        created.append(inc.code)
    _record(db, f"{len(created)} ocorrências geradas", now)
    db.commit()
    return {"created_incidents": created}
