"""Smart alerts: every alert is produced by an explicit rule from app.rules.engine."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Courier, Incident
from app.models.enums import OPEN_INCIDENT_STATUSES, CourierStatus, OrderStatus, Priority
from app.rules.engine import RuleConfig, capacity_alert, incident_is_stale_critical
from app.services.orders import active_orders
from app.services.restaurants import restaurant_stats

LEVELS = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def compute_alerts(db: Session, now: datetime, cfg: RuleConfig) -> list[dict]:
    alerts: list[dict] = []
    active = active_orders(db, now, cfg)
    delayed = [o for o, a in active if a.is_delayed]
    at_risk = [o for o, a in active if a.at_risk]
    waiting = [o for o, _ in active if o.courier_id is None and o.status in (OrderStatus.READY_FOR_PICKUP, OrderStatus.WAITING_COURIER)]
    available = db.scalar(select(func.count()).select_from(Courier).where(Courier.status == CourierStatus.AVAILABLE)) or 0

    def add(rule: str, level: str, title: str, message: str, orders: list[str] | None = None):
        alerts.append({"id": rule, "rule": rule, "level": level, "title": title, "message": message,
                       "orders": orders or []})

    if delayed:
        level = "CRITICAL" if len(delayed) >= cfg.delayed_orders_critical_count else "WARNING"
        add("ORDERS_DELAYED", level, "Pedidos atrasados",
            f"{_plural(len(delayed), 'pedido está atrasado', 'pedidos estão atrasados')} em relação ao prazo estimado.",
            [o.code for o in delayed])
    if at_risk:
        add("ORDERS_AT_RISK", "WARNING", "Risco de atraso",
            f"{_plural(len(at_risk), 'pedido está próximo', 'pedidos estão próximos')} de ultrapassar o prazo estimado.",
            [o.code for o in at_risk])
    if waiting:
        add("ORDERS_WITHOUT_COURIER", "CRITICAL" if len(waiting) >= 3 else "WARNING", "Pedidos sem entregador",
            f"{_plural(len(waiting), 'pedido está aguardando', 'pedidos estão aguardando')} atribuição de entregador.",
            [o.code for o in waiting])
    cap = capacity_alert(available, len(waiting))
    if cap == "NO_COURIERS":
        add("CAPACITY_NO_COURIERS", "CRITICAL", "Capacidade de entregadores esgotada",
            "Nenhum entregador disponível no momento.")
    elif cap == "INSUFFICIENT_COURIERS":
        add("CAPACITY_INSUFFICIENT", "WARNING", "Capacidade limitada",
            f"Há {len(waiting)} pedidos aguardando entregador e apenas {available} disponíveis.")

    for r in restaurant_stats(db, now, cfg)["restaurants"]:
        if r["prep_alert"]:
            add("RESTAURANT_SLOW_PREP", "WARNING", f"Preparo lento: {r['name']}",
                f"Restaurante {r['name']} apresenta tempo médio de preparação {r['prep_alert_pct']:.0f}% superior à média operacional.")

    stale = [(inc, (now - inc.created_at).total_seconds() / 60)
             for inc in db.scalars(select(Incident).where(Incident.status.in_(OPEN_INCIDENT_STATUSES),
                                                          Incident.priority == Priority.CRITICAL))]
    stale = [(i, m) for i, m in stale if incident_is_stale_critical(i.priority, m, cfg)]
    if stale:
        oldest = max(m for _, m in stale)
        add("INCIDENT_STALE", "CRITICAL", "Ocorrências críticas em aberto",
            f"{_plural(len(stale), 'ocorrência crítica permanece aberta', 'ocorrências críticas permanecem abertas')} "
            f"há mais de {cfg.critical_incident_open_minutes:.0f} min (a mais antiga há {oldest:.0f} min): "
            + ", ".join(i.code for i, _ in stale) + ".")

    if not alerts:
        add("ALL_CLEAR", "INFO", "Operação estável", "Nenhuma regra de alerta foi acionada neste momento.")
    alerts.sort(key=lambda a: -LEVELS[a["level"]])
    return alerts
