"""Deterministic demo data. Everything here is fictitious.

Orders are generated around the *current* (simulated) time so that every operational
situation exists at the moment of seeding: normal, delayed, at-risk, waiting for a
courier, cancelled and delivered orders.
"""
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    AgentConversation,
    AgentToolExecution,
    Courier,
    Customer,
    Incident,
    OperationalEvent,
    Order,
    OrderEvent,
    OrderItem,
    Restaurant,
    SimulationState,
    User,
)
from app.models.enums import (
    CourierStatus,
    IncidentStatus,
    IncidentType,
    OrderStatus,
    Priority,
    RestaurantStatus,
    Severity,
    UserRole,
)

CENTER = (-23.5505, -46.6333)  # fictitious city grid around a generic centre point

RESTAURANTS = [
    ("Sabor Urbano", "Brasileira", 22, 1.0), ("Pizzaria Forno Azul", "Pizza", 26, 1.0),
    ("Burger Lab 21", "Hambúrguer", 18, 1.0), ("Sushi Aurora", "Japonesa", 28, 1.0),
    ("Cantina Bella Massa", "Italiana", 24, 1.0), ("Veggie Horizonte", "Vegetariana", 20, 1.0),
    ("Taco Sol", "Mexicana", 17, 1.0), ("Churrasco do Vale", "Churrasco", 30, 1.0),
    ("Doce Canela", "Sobremesas", 12, 1.0), ("Açaí Tropical", "Açaí", 8, 1.0),
    ("Wok Express", "Oriental", 19, 1.0), ("Padaria Pão & Prosa", "Padaria", 10, 1.0),
    ("Marmita da Vovó", "Caseira", 21, 1.0), ("Kebab Oásis", "Árabe", 16, 1.0),
    ("Poke Mar Azul", "Saudável", 14, 1.0), ("Hot Dog Central", "Lanches", 11, 1.0),
]
SLOW_RESTAURANTS = {"Sabor Urbano": 1.9, "Churrasco do Vale": 1.7}  # preparation slower than baseline

FIRST = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabi", "Hugo", "Irene", "João", "Karen", "Lucas",
         "Marta", "Nuno", "Olívia", "Paulo", "Quésia", "Rafael", "Sofia", "Tiago", "Úrsula", "Vitor", "Wanda", "Yuri"]
LAST = ["Almeida", "Borges", "Campos", "Duarte", "Esteves", "Farias", "Gomes", "Horta", "Ibarra", "Junqueira",
        "Klein", "Lopes", "Moraes", "Nogueira", "Ortiz", "Pires", "Queiroz", "Ramos", "Soares", "Teixeira"]
DISHES = [("Prato do dia", 32.0), ("Combo família", 79.9), ("Refrigerante 600ml", 7.5), ("Sobremesa da casa", 14.0),
          ("Porção grande", 27.5), ("Suco natural", 9.9), ("Executivo", 28.9), ("Prato vegano", 34.0), ("Entrada mista", 21.0)]
STREETS = ["Rua das Acácias", "Av. Central", "Rua do Comércio", "Alameda dos Ipês", "Rua Nova Esperança",
           "Av. das Palmeiras", "Rua Sete de Setembro", "Travessa do Sol"]


def _pt(rng: random.Random, spread=0.045) -> tuple[float, float]:
    return CENTER[0] + rng.uniform(-spread, spread), CENTER[1] + rng.uniform(-spread, spread)


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def wipe(db: Session) -> None:
    for model in (AgentToolExecution, AgentConversation, OperationalEvent, Incident, OrderItem, OrderEvent, Order, Customer, Courier,
                  Restaurant, SimulationState):
        db.execute(delete(model))
    db.flush()


def ensure_users(db: Session) -> None:
    """Demo users exist ONLY outside production. In production, bootstrap from env."""
    s = get_settings()
    now = datetime.now(UTC)
    wanted: list[tuple[str, str, str, UserRole]] = []
    if not s.is_production:
        wanted = [
            ("admin@opspilot.local", "Admin Demo", "opspilot-demo", UserRole.ADMIN),
            ("operador@opspilot.local", "Operador Demo", "opspilot-demo", UserRole.OPERATOR),
            ("viewer@opspilot.local", "Visualizador Demo", "opspilot-demo", UserRole.VIEWER),
        ]
    elif s.admin_email and s.admin_password:
        wanted = [(s.admin_email, "Administrador", s.admin_password, UserRole.ADMIN)]
    for email, name, pwd, role in wanted:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, full_name=name, hashed_password=hash_password(pwd), role=role, created_at=now))
    db.flush()


def seed_demo(db: Session, seed: int = 42, now: datetime | None = None) -> dict:
    rng = random.Random(seed)
    now = now or datetime.now(UTC)
    db.add(SimulationState(id=1, offset_minutes=0.0, last_action="seed", updated_at=now))

    restaurants = []
    for i, (name, cat, prep, _) in enumerate(RESTAURANTS, start=1):
        lat, lng = _pt(rng)
        r = Restaurant(
            code=f"R-{i:03d}", name=name, category=cat, address=f"{rng.choice(STREETS)}, {rng.randint(10, 999)}",
            lat=lat, lng=lng, status=RestaurantStatus.BUSY if name in SLOW_RESTAURANTS else RestaurantStatus.OPEN,
            avg_prep_minutes=prep, rating=round(rng.uniform(3.8, 4.9), 1),
            delay_factor=SLOW_RESTAURANTS.get(name, 1.0), created_at=now - timedelta(days=90),
        )
        restaurants.append(r)
    restaurants[-1].status = RestaurantStatus.PAUSED
    db.add_all(restaurants)

    couriers = []
    for i in range(1, 35):
        lat, lng = _pt(rng, 0.05)
        couriers.append(Courier(
            code=f"E-{i:03d}", name=_name(rng), status=CourierStatus.AVAILABLE, lat=lat, lng=lng,
            total_deliveries=rng.randint(20, 400), avg_delivery_minutes=round(rng.uniform(18, 34), 1),
            updated_at=now - timedelta(minutes=rng.randint(1, 25)),
        ))
    db.add_all(couriers)
    db.flush()

    state = {"n": 1000, "free": list(couriers)}

    def take_courier():
        return state["free"].pop() if state["free"] else None

    def make_order(created_ago: float, status: OrderStatus, *, restaurant=None, with_courier=None,
                   late_by: float | None = None, remaining: float | None = None, cancel_reason=None,
                   slow=False) -> Order:
        state["n"] += 1
        rest = restaurant or rng.choice([r for r in restaurants if r.status != RestaurantStatus.PAUSED])
        lat, lng = _pt(rng)
        cust = Customer(name=_name(rng), phone=f"+55 11 9{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
                        address=f"{rng.choice(STREETS)}, {rng.randint(10, 999)}", lat=lat, lng=lng)
        est_prep = int(rest.avg_prep_minutes + rng.randint(-2, 3))
        travel = rng.randint(12, 24)
        est_total = est_prep + travel + 8
        created = now - timedelta(minutes=created_ago)
        if late_by is not None:           # promised time already passed by `late_by` minutes
            est_total = int(created_ago - late_by)
        elif remaining is not None:       # promised time is `remaining` minutes ahead
            est_total = int(created_ago + remaining)
        sim_prep = est_prep * rest.delay_factor * (1.15 if slow else 1.0) + rng.uniform(-1, 2)
        sim_travel = travel + rng.uniform(-2, 4)
        o = Order(
            code=f"ORD-{state['n']}", restaurant=rest, customer=cust, status=OrderStatus.RECEIVED,
            total_amount=0, est_prep_minutes=est_prep, est_delivery_minutes=est_total,
            created_at=created, promised_at=created + timedelta(minutes=est_total), updated_at=created,
            sim_prep_minutes=round(max(sim_prep, 4), 1), sim_travel_minutes=round(max(sim_travel, 6), 1),
        )
        total = 0.0
        for name, price in rng.sample(DISHES, rng.randint(1, 3)):
            q = rng.randint(1, 2)
            o.items.append(OrderItem(name=name, quantity=q, unit_price=price))
            total += q * price
        o.total_amount = round(total, 2)

        t = created
        o.events.append(OrderEvent(event_type="CREATED", to_status="RECEIVED", message="Pedido recebido", created_at=t))

        def step(to: OrderStatus, at: datetime, msg: str | None = None):
            o.events.append(OrderEvent(event_type="STATUS_CHANGED", from_status=o.status.value, to_status=to.value,
                                       message=msg or f"Status alterado de {o.status.value} para {to.value}", created_at=at))
            o.status, o.updated_at = to, at

        order = [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP,
                 OrderStatus.WAITING_COURIER, OrderStatus.IN_DELIVERY, OrderStatus.DELIVERED]
        if status == OrderStatus.CANCELLED:
            step(OrderStatus.CONFIRMED, created + timedelta(minutes=2))
            at = created + timedelta(minutes=rng.randint(4, 14))
            step(OrderStatus.CANCELLED, at, f"Status alterado para CANCELLED: {cancel_reason}")
            o.cancelled_at, o.cancel_reason = at, cancel_reason
            return o
        target = order.index(status) if status in order else -1
        if status == OrderStatus.RECEIVED:
            return o
        prep_done = created + timedelta(minutes=sim_prep + 2)
        for st in order[: target + 1]:
            if st == OrderStatus.CONFIRMED:
                step(st, created + timedelta(minutes=2))
            elif st == OrderStatus.PREPARING:
                step(st, created + timedelta(minutes=4))
            elif st == OrderStatus.READY_FOR_PICKUP:
                o.ready_at = min(prep_done, now) if status != OrderStatus.DELIVERED else prep_done
                step(st, o.ready_at)
            elif st == OrderStatus.WAITING_COURIER:
                step(st, o.ready_at + timedelta(minutes=1))
            elif st == OrderStatus.IN_DELIVERY:
                o.picked_up_at = (o.ready_at or created) + timedelta(minutes=rng.randint(2, 5))
                if o.picked_up_at > now:
                    o.picked_up_at = now - timedelta(minutes=1)
                step(st, o.picked_up_at)
            elif st == OrderStatus.DELIVERED:
                o.delivered_at = o.picked_up_at + timedelta(minutes=sim_travel)
                step(st, o.delivered_at)
        if with_courier is not None:
            o.courier = with_courier
            o.events.append(OrderEvent(event_type="COURIER_ASSIGNED", message=f"Entregador {with_courier.code} atribuído",
                                       created_at=(o.ready_at or created) + timedelta(minutes=1)))
        return o

    orders: list[Order] = []

    # --- history: delivered / cancelled over the last 72h (peaks at lunch/dinner are approximated by randomness)
    for _ in range(62):
        ago = rng.choice([rng.uniform(130, 1400), rng.uniform(130, 4200)])
        orders.append(make_order(ago, OrderStatus.DELIVERED, with_courier=rng.choice(couriers)))
    reasons = ["Cliente desistiu", "Restaurante sem insumos", "Endereço inválido", "Pagamento recusado"]
    for _ in range(9):
        orders.append(make_order(rng.uniform(60, 2500), OrderStatus.CANCELLED, cancel_reason=rng.choice(reasons)))

    # --- active situations
    for _ in range(8):  # healthy preparing / in progress
        ago = rng.uniform(3, 9)
        orders.append(make_order(ago, rng.choice([OrderStatus.RECEIVED, OrderStatus.CONFIRMED, OrderStatus.PREPARING]),
                                 remaining=rng.uniform(32, 45)))
    for _ in range(9):  # healthy in delivery
        c = take_courier(); c.status = CourierStatus.DELIVERING
        orders.append(make_order(rng.uniform(22, 30), OrderStatus.IN_DELIVERY, with_courier=c, remaining=rng.uniform(12, 20)))
    for _ in range(3):  # healthy picking up
        c = take_courier(); c.status = CourierStatus.ASSIGNED
        orders.append(make_order(rng.uniform(18, 22), OrderStatus.READY_FOR_PICKUP, with_courier=c, remaining=rng.uniform(18, 26)))
    for late in (4, 9, 14, 22, 37, 52):  # delayed (assorted severities)
        c = take_courier(); c.status = CourierStatus.DELIVERING
        orders.append(make_order(late + rng.uniform(40, 50), OrderStatus.IN_DELIVERY, with_courier=c, late_by=late))
    orders.append(make_order(70, OrderStatus.PREPARING, restaurant=restaurants[0], late_by=18))       # slow kitchen
    for rem in (4, 7, 9):  # at risk: close to deadline, still preparing / no courier
        orders.append(make_order(30, OrderStatus.PREPARING, remaining=rem))
    orders.append(make_order(28, OrderStatus.READY_FOR_PICKUP, remaining=12))
    for ago in (30, 24, 20):  # waiting for courier w/o courier
        orders.append(make_order(ago, OrderStatus.WAITING_COURIER, remaining=rng.uniform(9, 16)))
    orders.append(make_order(12, OrderStatus.PREPARING, restaurant=restaurants[7], remaining=40, slow=True))
    orders.append(make_order(2, OrderStatus.RECEIVED, remaining=45))
    orders.append(make_order(3, OrderStatus.CONFIRMED, remaining=44))

    # a few couriers offline, to make capacity visible
    for c in state["free"][-5:]:
        c.status = CourierStatus.OFFLINE
    db.add_all(orders)
    db.flush()

    # --- incidents
    def inc(code_n, typ, prio, status, title, desc, order=None, assignee=None, minutes_ago=30, resolution=None):
        created = now - timedelta(minutes=minutes_ago)
        i = Incident(code=f"OP-{code_n:03d}", type=typ, priority=prio, status=status, title=title, description=desc,
                     assignee=assignee, resolution=resolution, created_by="seed", created_at=created, updated_at=created,
                     order_id=order.id if order else None, restaurant_id=order.restaurant_id if order else None,
                     resolved_at=created + timedelta(minutes=20) if status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) else None)
        db.add(i)
        db.add(OperationalEvent(event_type="INCIDENT_CREATED", severity=Severity.INFO if prio in (Priority.LOW, Priority.MEDIUM) else Severity.WARNING,
                                message=f"Ocorrência {i.code} aberta ({title})", entity_type="incident",
                                entity_id=str(i.id), payload={"code": i.code}, created_at=created))
        db.flush()
        return i

    delayed = [o for o in orders if o.status == OrderStatus.IN_DELIVERY and o.promised_at < now]
    types = list(IncidentType)
    n = 1
    for k, o in enumerate(delayed):
        prio = Priority.CRITICAL if k == len(delayed) - 1 else Priority.HIGH if k > 2 else Priority.MEDIUM
        inc(n, IncidentType.DELIVERY_DELAY, prio, IncidentStatus.OPEN if k % 2 == 0 else IncidentStatus.INVESTIGATING,
            "Atraso na entrega", f"Pedido {o.code} ultrapassou o prazo estimado.", o,
            assignee="Operador Demo" if k % 2 else None, minutes_ago=45 + k * 11)
        n += 1
    statuses = [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.WAITING_ACTION, IncidentStatus.RESOLVED, IncidentStatus.CLOSED]
    while n <= 24:
        typ = types[n % len(types)]
        st = statuses[n % len(statuses)]
        o = rng.choice(orders)
        inc(n, typ, rng.choice(list(Priority)), st, "Ocorrência de demonstração",
            f"Registro fictício de {typ.value.lower().replace('_', ' ')} relacionado ao pedido {o.code}.", o,
            assignee="Operador Demo" if st != IncidentStatus.OPEN else None, minutes_ago=rng.randint(60, 1500),
            resolution="Resolvido com contato ao cliente." if st in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) else None)
        n += 1

    # --- activity feed from order events (most recent)
    for o in orders:
        for e in o.events:
            if e.to_status in ("DELIVERED", "CANCELLED") and (now - e.created_at) < timedelta(hours=3):
                db.add(OperationalEvent(
                    event_type="ORDER_STATUS", severity=Severity.WARNING if e.to_status == "CANCELLED" else Severity.INFO,
                    message=f"Pedido {o.code}: {'concluído' if e.to_status == 'DELIVERED' else 'cancelado'}",
                    entity_type="order", entity_id=str(o.id), payload={"code": o.code}, created_at=e.created_at))
    for o in orders:
        if o.status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED) and o.promised_at < now:
            db.add(OperationalEvent(event_type="ORDER_DELAYED", severity=Severity.WARNING,
                                    message=f"Pedido {o.code} entrou em situação de atraso", entity_type="order",
                                    entity_id=str(o.id), payload={"code": o.code}, created_at=o.promised_at))
    db.flush()
    return {"restaurants": len(restaurants), "couriers": len(couriers), "orders": len(orders),
            "incidents": db.query(Incident).count()}


def reset_demo(db: Session, seed: int = 42) -> dict:
    wipe(db)
    ensure_users(db)
    result = seed_demo(db, seed)
    db.commit()
    return result
