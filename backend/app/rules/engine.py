"""Operational business rules.

Pure functions over plain snapshots: no database, no HTTP, no prompts. Every threshold
lives in `RuleConfig` so rules are configurable (env `RULES_OVERRIDES`) and unit-testable.
"""
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime

from app.models.enums import (
    ACTIVE_STATUSES,
    OrderStatus,
    Priority,
)

PRE_DELIVERY = (
    OrderStatus.RECEIVED,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY_FOR_PICKUP,
    OrderStatus.WAITING_COURIER,
)

ALLOWED_TRANSITIONS: dict[OrderStatus, tuple[OrderStatus, ...]] = {
    OrderStatus.RECEIVED: (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
    OrderStatus.CONFIRMED: (OrderStatus.PREPARING, OrderStatus.CANCELLED),
    OrderStatus.PREPARING: (OrderStatus.READY_FOR_PICKUP, OrderStatus.CANCELLED),
    OrderStatus.READY_FOR_PICKUP: (OrderStatus.WAITING_COURIER, OrderStatus.IN_DELIVERY, OrderStatus.CANCELLED),
    OrderStatus.WAITING_COURIER: (OrderStatus.IN_DELIVERY, OrderStatus.CANCELLED),
    OrderStatus.IN_DELIVERY: (OrderStatus.DELIVERED, OrderStatus.CANCELLED),
    OrderStatus.DELIVERED: (),
    OrderStatus.CANCELLED: (),
}


@dataclass(frozen=True)
class RuleConfig:
    # Delay priority: minutes late above which the priority escalates.
    delay_medium_minutes: float = 5
    delay_high_minutes: float = 15
    delay_critical_minutes: float = 30
    # At-risk rules
    risk_remaining_minutes: float = 10  # pre-delivery order with <= N min to deadline
    risk_in_delivery_remaining_minutes: float = 3
    risk_no_courier_remaining_minutes: float = 15  # no courier and <= N min to deadline
    courier_wait_minutes: float = 8  # ready/waiting for a courier for >= N min
    prep_overrun_minutes: float = 5  # preparing for > estimate + N min
    # Restaurant alert
    restaurant_prep_factor: float = 1.3  # observed prep >= factor * operation average
    restaurant_min_orders: int = 3
    # Capacity / incidents
    critical_incident_open_minutes: float = 30
    delayed_orders_critical_count: int = 5
    # Courier recommendation
    max_courier_distance_km: float = 8.0

    @classmethod
    def from_overrides(cls, overrides: dict[str, float] | None) -> "RuleConfig":
        valid = {f.name: f.type for f in fields(cls)}
        clean = {}
        for k, v in (overrides or {}).items():
            if k not in valid:
                raise ValueError(f"Unknown rule setting: {k}")
            clean[k] = int(v) if valid[k] in (int, "int") else float(v)
        return replace(cls(), **clean)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrderSnapshot:
    status: OrderStatus
    created_at: datetime
    promised_at: datetime
    est_prep_minutes: float
    has_courier: bool
    ready_at: datetime | None = None


@dataclass(frozen=True)
class OrderAssessment:
    is_delayed: bool
    delay_minutes: float
    priority: Priority | None
    at_risk: bool
    risk_reasons: tuple[str, ...]
    remaining_minutes: float | None  # until promised time (negative when late)


def _minutes(delta) -> float:
    return delta.total_seconds() / 60.0


def delay_priority(delay_minutes: float, cfg: RuleConfig) -> Priority:
    if delay_minutes >= cfg.delay_critical_minutes:
        return Priority.CRITICAL
    if delay_minutes >= cfg.delay_high_minutes:
        return Priority.HIGH
    if delay_minutes >= cfg.delay_medium_minutes:
        return Priority.MEDIUM
    return Priority.LOW


def is_valid_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assess_order(o: OrderSnapshot, now: datetime, cfg: RuleConfig) -> OrderAssessment:
    """Classify an order as delayed / at risk, with human-readable reasons."""
    if o.status not in ACTIVE_STATUSES:
        return OrderAssessment(False, 0.0, None, False, (), None)

    remaining = _minutes(o.promised_at - now)
    if remaining < 0:
        late = -remaining
        return OrderAssessment(True, round(late, 1), delay_priority(late, cfg), False, (), round(remaining, 1))

    reasons: list[str] = []
    if o.status in PRE_DELIVERY and remaining <= cfg.risk_remaining_minutes:
        reasons.append(f"Faltam {remaining:.0f} min para o prazo e o pedido ainda não saiu para entrega")
    if o.status == OrderStatus.IN_DELIVERY and remaining <= cfg.risk_in_delivery_remaining_minutes:
        reasons.append(f"Entrega em curso com apenas {remaining:.0f} min até o prazo")
    if o.status in PRE_DELIVERY and not o.has_courier and remaining <= cfg.risk_no_courier_remaining_minutes:
        reasons.append(f"Sem entregador atribuído e restam {remaining:.0f} min")
    if o.status in (OrderStatus.READY_FOR_PICKUP, OrderStatus.WAITING_COURIER) and o.ready_at:
        waited = _minutes(now - o.ready_at)
        if waited >= cfg.courier_wait_minutes:
            reasons.append(f"Pronto para retirada há {waited:.0f} min aguardando entregador")
    if o.status == OrderStatus.PREPARING:
        elapsed = _minutes(now - o.created_at)
        over = elapsed - o.est_prep_minutes
        if over > cfg.prep_overrun_minutes:
            reasons.append(f"Preparo excedeu a estimativa em {over:.0f} min")
    return OrderAssessment(False, 0.0, None, bool(reasons), tuple(reasons), round(remaining, 1))


def restaurant_prep_alert(
    observed_avg: float | None, operation_avg: float | None, order_count: int, cfg: RuleConfig
) -> float | None:
    """Return the percentage above the operation average if the restaurant is slow, else None."""
    if observed_avg is None or not operation_avg or order_count < cfg.restaurant_min_orders:
        return None
    if observed_avg >= operation_avg * cfg.restaurant_prep_factor:
        return round((observed_avg / operation_avg - 1) * 100, 1)
    return None


def capacity_alert(available_couriers: int, orders_waiting_courier: int) -> str | None:
    if available_couriers == 0:
        return "NO_COURIERS"
    if orders_waiting_courier > available_couriers:
        return "INSUFFICIENT_COURIERS"
    return None


def incident_is_stale_critical(priority: Priority, open_minutes: float, cfg: RuleConfig) -> bool:
    return priority == Priority.CRITICAL and open_minutes >= cfg.critical_incident_open_minutes
