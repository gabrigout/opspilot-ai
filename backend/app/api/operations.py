"""Orders, couriers and restaurants endpoints."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, current_user, get_ctx, require_writer
from app.core.errors import NotFoundError
from app.models import User
from app.models.enums import CourierStatus, OrderStatus, RestaurantStatus
from app.schemas.inputs import AssignIn, CourierStatusIn, OrderStatusIn
from app.services import couriers as courier_svc
from app.services import orders as order_svc
from app.services.restaurants import restaurant_stats

router = APIRouter(dependencies=[Depends(current_user)])


# ------------------------------------------------------------------ orders
@router.get("/orders", tags=["orders"], summary="Lista pedidos com filtros e paginação")
def list_orders(
    status: OrderStatus | None = None,
    restaurant: str | None = Query(None, description="UUID, código ou nome"),
    q: str | None = Query(None, max_length=40, description="Busca por código"),
    situation: str | None = Query(None, pattern="^(delayed|at_risk|on_track)$"),
    period_hours: int | None = Query(None, ge=1, le=720),
    since: datetime | None = None,
    until: datetime | None = None,
    no_courier: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    ctx: Ctx = Depends(get_ctx),
):
    if period_hours and not since:
        since = ctx.now - timedelta(hours=period_hours)
    rows = order_svc.query_orders(ctx.db, ctx.now, ctx.cfg, status=status, restaurant=restaurant, q=q,
                                  since=since, until=until, situation=situation, no_courier=no_courier)
    start = (page - 1) * page_size
    return {"items": [order_svc.order_summary(o, ctx.now, ctx.cfg) for o, _ in rows[start:start + page_size]],
            "total": len(rows), "page": page, "page_size": page_size}


@router.get("/orders/{order_id}", tags=["orders"], summary="Detalhe do pedido (UUID ou código)")
def get_order(order_id: str, ctx: Ctx = Depends(get_ctx)):
    return order_svc.order_detail(order_svc.find_order(ctx.db, order_id, detail=True), ctx.now, ctx.cfg)


@router.get("/orders/{order_id}/history", tags=["orders"], summary="Histórico de eventos do pedido")
def order_history(order_id: str, ctx: Ctx = Depends(get_ctx)):
    o = order_svc.find_order(ctx.db, order_id, detail=True)
    return {"order_code": o.code, "events": [order_svc.event_out(e) for e in o.events]}


@router.patch("/orders/{order_id}/status", tags=["orders"], summary="Atualiza o status validando a transição")
def update_status(order_id: str, body: OrderStatusIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(require_writer)):
    o = order_svc.find_order(ctx.db, order_id, detail=True)
    order_svc.change_status(ctx.db, o, body.status, ctx.now, user.email, body.reason)
    ctx.db.commit()
    return order_svc.order_detail(o, ctx.now, ctx.cfg)


@router.get("/orders/{order_id}/courier-recommendations", tags=["orders", "couriers"],
            summary="Ranking de entregadores para o pedido (não atribui)")
def courier_recommendations(order_id: str, limit: int = Query(5, ge=1, le=15), ctx: Ctx = Depends(get_ctx)):
    return courier_svc.recommend(ctx.db, order_svc.find_order(ctx.db, order_id), ctx.now, ctx.cfg, limit)


@router.post("/orders/{order_id}/assign", tags=["orders", "couriers"], summary="Atribui um entregador (aprovação humana)")
def assign(order_id: str, body: AssignIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(require_writer)):
    o = order_svc.find_order(ctx.db, order_id, detail=True)
    order_svc.assign_courier(ctx.db, o, courier_svc.get_courier(ctx.db, body.courier_id), ctx.now, user.email)
    ctx.db.commit()
    return order_svc.order_detail(o, ctx.now, ctx.cfg)


# ------------------------------------------------------------------ couriers
@router.get("/couriers", tags=["couriers"], summary="Lista entregadores")
def list_couriers(status: CourierStatus | None = None, ctx: Ctx = Depends(get_ctx)):
    items = courier_svc.list_couriers(ctx.db, ctx.now, status)
    summary: dict[str, int] = {}
    for c in courier_svc.list_couriers(ctx.db, ctx.now):
        summary[c["status"]] = summary.get(c["status"], 0) + 1
    return {"items": items, "total": len(items), "summary": summary}


@router.get("/couriers/available", tags=["couriers"], summary="Entregadores disponíveis")
def available_couriers(ctx: Ctx = Depends(get_ctx)):
    items = courier_svc.list_couriers(ctx.db, ctx.now, CourierStatus.AVAILABLE)
    return {"items": items, "total": len(items), "shortage": len(items) == 0}


@router.get("/couriers/{courier_id}", tags=["couriers"], summary="Detalhe, pedidos associados e histórico")
def courier_detail(courier_id: str, ctx: Ctx = Depends(get_ctx)):
    c = courier_svc.get_courier(ctx.db, courier_id)
    rows = order_svc.query_orders(ctx.db, ctx.now, ctx.cfg, courier_id=c.id)
    counts = courier_svc.active_counts(ctx.db)
    return {**courier_svc.courier_out(c, counts.get(c.id, 0), ctx.now),
            "recent_orders": [order_svc.order_summary(o, ctx.now, ctx.cfg) for o, _ in rows[:30]]}


@router.patch("/couriers/{courier_id}/status", tags=["couriers"], summary="Atualiza o status do entregador")
def courier_status(courier_id: str, body: CourierStatusIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(require_writer)):
    c = courier_svc.set_status(ctx.db, courier_svc.get_courier(ctx.db, courier_id), body.status, ctx.now, user.email)
    ctx.db.commit()
    return courier_svc.courier_out(c, courier_svc.active_counts(ctx.db).get(c.id, 0), ctx.now)


# ------------------------------------------------------------------ restaurants
@router.get("/restaurants", tags=["restaurants"], summary="Lista restaurantes com métricas de desempenho")
def list_restaurants(status: RestaurantStatus | None = None, period_hours: int = Query(24, ge=1, le=720),
                     ctx: Ctx = Depends(get_ctx)):
    st = restaurant_stats(ctx.db, ctx.now, ctx.cfg, period_hours)
    items = [r for r in st["restaurants"] if not status or r["status"] == status.value]
    return {"items": items, "total": len(items), "operation_avg_prep_minutes": st["operation_avg_prep_minutes"],
            "period_hours": period_hours}


@router.get("/restaurants/{restaurant_id}", tags=["restaurants"], summary="Detalhe e pedidos relacionados")
def restaurant_detail(restaurant_id: str, period_hours: int = Query(24, ge=1, le=720), ctx: Ctx = Depends(get_ctx)):
    r = order_svc.find_restaurant(ctx.db, restaurant_id)
    st = restaurant_stats(ctx.db, ctx.now, ctx.cfg, period_hours)
    row = next(x for x in st["restaurants"] if x["id"] == str(r.id))
    rows = order_svc.query_orders(ctx.db, ctx.now, ctx.cfg, restaurant=str(r.id))
    if not row:
        raise NotFoundError("Restaurant not found")
    return {**row, "operation_avg_prep_minutes": st["operation_avg_prep_minutes"], "period_hours": period_hours,
            "recent_orders": [order_svc.order_summary(o, ctx.now, ctx.cfg) for o, _ in rows[:30]]}
