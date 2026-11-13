"""The 12 agent tools. Handlers only call the service layer (no raw SQL, no side channels)."""
from datetime import timedelta

from pydantic import BaseModel, Field, model_validator

from app.models.enums import IncidentType, OrderStatus, Priority
from app.services import couriers as courier_svc
from app.services import incidents as incident_svc
from app.services import metrics, reports
from app.services import orders as order_svc
from app.services.restaurants import restaurant_stats
from app.tools.base import Tool, ToolContext, register

MAX_LIMIT = 50


class OrderRef(BaseModel):
    order_id: str | None = Field(None, description="UUID do pedido")
    order_code: str | None = Field(None, description="Código do pedido, ex.: ORD-1042 ou #1042")

    @model_validator(mode="after")
    def _one(self):
        if not (self.order_id or self.order_code):
            raise ValueError("order_id or order_code is required")
        return self

    @property
    def ident(self) -> str:
        return (self.order_id or self.order_code or "").strip()


class Limit(BaseModel):
    limit: int = Field(10, ge=1, le=MAX_LIMIT, description="Máximo de resultados")


def _brief(o: dict) -> dict:
    keys = ("code", "status", "situation", "restaurant", "courier", "delay_minutes", "delay_priority",
            "remaining_minutes", "risk_reasons", "promised_at")
    d = {k: o[k] for k in keys if k in o}
    d["restaurant"] = o["restaurant"]["name"]
    d["courier"] = o["courier"]["code"] if o["courier"] else None
    return d


# 1 ------------------------------------------------------------------ get_order
def get_order(ctx: ToolContext, a: OrderRef) -> dict:
    o = order_svc.find_order(ctx.db, a.ident, detail=True)
    d = order_svc.order_detail(o, ctx.now, ctx.cfg)
    d.pop("history")
    return d


# 2 ------------------------------------------------------------------ search_orders
class SearchOrdersArgs(Limit):
    status: OrderStatus | None = None
    situation: str | None = Field(None, pattern="^(delayed|at_risk|on_track)$")
    restaurant: str | None = Field(None, max_length=80, description="Nome, código ou UUID do restaurante")
    period_hours: int | None = Field(None, ge=1, le=720, description="Considerar pedidos criados nas últimas N horas")


def search_orders(ctx: ToolContext, a: SearchOrdersArgs) -> dict:
    since = ctx.now - timedelta(hours=a.period_hours) if a.period_hours else None
    rows = order_svc.query_orders(ctx.db, ctx.now, ctx.cfg, status=a.status, restaurant=a.restaurant,
                                  since=since, situation=a.situation)
    by_status: dict[str, int] = {}
    for o, _ in rows:
        by_status[o.status.value] = by_status.get(o.status.value, 0) + 1
    return {"total_found": len(rows), "returned": min(len(rows), a.limit), "by_status": by_status,
            "orders": [_brief(order_svc.order_summary(o, ctx.now, ctx.cfg)) for o, _ in rows[: a.limit]]}


# 3 ------------------------------------------------------------------ get_delayed_orders
def get_delayed_orders(ctx: ToolContext, a: Limit) -> dict:
    rows = [(o, x) for o, x in order_svc.active_orders(ctx.db, ctx.now, ctx.cfg) if x.is_delayed]
    rows.sort(key=lambda t: -t[1].delay_minutes)
    return {"total_delayed": len(rows), "orders": [
        {**_brief(order_svc.order_summary(o, ctx.now, ctx.cfg)), "customer": o.customer.name,
         "estimated_delivery_minutes": o.est_delivery_minutes} for o, _ in rows[: a.limit]]}


# 4 ------------------------------------------------------------------ get_at_risk_orders
def get_at_risk_orders(ctx: ToolContext, a: Limit) -> dict:
    rows = [(o, x) for o, x in order_svc.active_orders(ctx.db, ctx.now, ctx.cfg) if x.at_risk]
    rows.sort(key=lambda t: t[1].remaining_minutes)
    return {"total_at_risk": len(rows), "orders": [
        _brief(order_svc.order_summary(o, ctx.now, ctx.cfg)) for o, _ in rows[: a.limit]]}


# 5 ------------------------------------------------------------------ get_available_couriers
def get_available_couriers(ctx: ToolContext, a: Limit) -> dict:
    rows = courier_svc.list_couriers(ctx.db, ctx.now)
    avail = [c for c in rows if c["status"] == "AVAILABLE"]
    counts: dict[str, int] = {}
    for c in rows:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return {"available_count": len(avail), "total_couriers": len(rows), "by_status": counts,
            "couriers": [{k: c[k] for k in ("code", "name", "status", "location", "active_orders", "idle_minutes")}
                         for c in avail[: a.limit]]}


# 6 ------------------------------------------------------------------ recommend_courier
class RecommendArgs(OrderRef):
    limit: int = Field(3, ge=1, le=10)


def recommend_courier(ctx: ToolContext, a: RecommendArgs) -> dict:
    o = order_svc.find_order(ctx.db, a.ident)
    return courier_svc.recommend(ctx.db, o, ctx.now, ctx.cfg, a.limit)


# 7 ------------------------------------------------------------------ get_restaurant_performance
class RestaurantArgs(BaseModel):
    restaurant: str = Field(..., min_length=1, max_length=80, description="Nome, código (R-001) ou UUID")
    period_hours: int = Field(24, ge=1, le=720)


def get_restaurant_performance(ctx: ToolContext, a: RestaurantArgs) -> dict:
    r = order_svc.find_restaurant(ctx.db, a.restaurant)
    st = restaurant_stats(ctx.db, ctx.now, ctx.cfg, a.period_hours)
    row = next(x for x in st["restaurants"] if x["id"] == str(r.id))
    return {**row, "operation_avg_prep_minutes": st["operation_avg_prep_minutes"], "period_hours": a.period_hours}


# 8 ------------------------------------------------------------------ get_operational_metrics
class MetricsArgs(BaseModel):
    period_hours: int = Field(24, ge=1, le=720)


def get_operational_metrics(ctx: ToolContext, a: MetricsArgs) -> dict:
    return metrics.kpis(ctx.db, ctx.now, ctx.cfg, a.period_hours)


# 9 ------------------------------------------------------------------ create_incident
class CreateIncidentArgs(BaseModel):
    order_code: str | None = Field(None, max_length=40, description="Pedido associado, quando aplicável")
    type: IncidentType
    description: str = Field(..., min_length=10, max_length=1000)
    priority: Priority


def create_incident(ctx: ToolContext, a: CreateIncidentArgs) -> dict:
    inc = incident_svc.create_incident(ctx.db, ctx.now, type=a.type, description=a.description, priority=a.priority,
                                       order_ref=a.order_code, actor=ctx.actor)
    return incident_svc.incident_out(inc)


# 10 ----------------------------------------------------------------- generate_operational_report
class ReportArgs(BaseModel):
    kind: str = Field("general", pattern="^(general|delays|restaurants|couriers|incidents)$")
    period_hours: int = Field(24, ge=1, le=720)


def generate_operational_report(ctx: ToolContext, a: ReportArgs) -> dict:
    rep = reports.build_report(ctx.db, a.kind, ctx.now, ctx.cfg, a.period_hours)
    rep["table"]["rows"] = rep["table"]["rows"][:15]  # keep tool output compact
    return rep


# 11 ----------------------------------------------------------------- get_open_incidents
class OpenIncidentsArgs(Limit):
    priority: Priority | None = None


def get_open_incidents(ctx: ToolContext, a: OpenIncidentsArgs) -> dict:
    rows = incident_svc.list_incidents(ctx.db, open_only=True, priority=a.priority)
    by_p: dict[str, int] = {}
    for i in rows:
        by_p[i.priority.value] = by_p.get(i.priority.value, 0) + 1
    return {"total_open": len(rows), "by_priority": by_p, "incidents": [
        {k: v for k, v in incident_svc.incident_out(i).items() if k in ("code", "type", "priority", "status", "title", "order", "assignee", "created_at")}
        for i in rows[: a.limit]]}


# 12 ----------------------------------------------------------------- get_order_history
def get_order_history(ctx: ToolContext, a: OrderRef) -> dict:
    o = order_svc.find_order(ctx.db, a.ident, detail=True)
    return {"order_code": o.code, "current_status": o.status.value,
            "events": [order_svc.event_out(e) for e in o.events]}


def _reg(name, desc, model, fn, mutates=False):
    register(Tool(name, desc, model, fn, mutates))


_reg("get_order", "Consulta os dados completos de um pedido (status, restaurante, entregador, prazos e situação operacional).", OrderRef, get_order)
_reg("search_orders", "Pesquisa pedidos por status, situação (delayed/at_risk/on_track), restaurante e período.", SearchOrdersArgs, search_orders)
_reg("get_delayed_orders", "Lista pedidos atrasados (prazo estimado ultrapassado), com tempo de atraso e prioridade.", Limit, get_delayed_orders)
_reg("get_at_risk_orders", "Lista pedidos com risco de atraso, com a justificativa de cada regra acionada.", Limit, get_at_risk_orders)
_reg("get_available_couriers", "Lista entregadores disponíveis com localização simulada e carga operacional.", Limit, get_available_couriers)
_reg("recommend_courier", "Classifica entregadores candidatos para um pedido (distância, carga, ociosidade). NÃO atribui automaticamente.", RecommendArgs, recommend_courier)
_reg("get_restaurant_performance", "Desempenho de um restaurante: pedidos, preparo médio, cancelamentos, atrasos e comparação com a média.", RestaurantArgs, get_restaurant_performance)
_reg("get_operational_metrics", "Indicadores gerais da operação para um período em horas.", MetricsArgs, get_operational_metrics)
_reg("create_incident", "Cria uma ocorrência operacional. Exige confirmação explícita do usuário antes de gravar.", CreateIncidentArgs, create_incident, mutates=True)
_reg("generate_operational_report", "Gera um relatório (general, delays, restaurants, couriers, incidents) com dados consultados.", ReportArgs, generate_operational_report)
_reg("get_open_incidents", "Lista ocorrências abertas e suas prioridades.", OpenIncidentsArgs, get_open_incidents)
_reg("get_order_history", "Retorna o histórico de eventos/alterações de um pedido.", OrderRef, get_order_history)
