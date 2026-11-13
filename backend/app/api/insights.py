"""Dashboard, incidents, reports, simulation, activity and settings endpoints."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import Ctx, current_user, get_ctx, require_admin, require_writer
from app.core.config import get_settings
from app.models import OperationalEvent, User
from app.models.enums import IncidentStatus, Priority, Severity
from app.schemas.inputs import AdvanceIn, IncidentCreateIn, IncidentUpdateIn, SimActionIn
from app.services import incidents as incident_svc
from app.services import metrics, reports, seed, simulation
from app.services.alerts import compute_alerts
from app.services.orders import iso

router = APIRouter(dependencies=[Depends(current_user)])
HOURS = Query(24, ge=1, le=720, description="Período em horas")


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard/overview", tags=["dashboard"], summary="KPIs, gráficos, alertas e atividade")
def overview(hours: int = HOURS, ctx: Ctx = Depends(get_ctx)):
    return metrics.overview(ctx.db, ctx.now, ctx.cfg, hours)


@router.get("/dashboard/metrics", tags=["dashboard"], summary="Indicadores calculados do banco")
def dashboard_metrics(hours: int = HOURS, ctx: Ctx = Depends(get_ctx)):
    return metrics.kpis(ctx.db, ctx.now, ctx.cfg, hours)


@router.get("/dashboard/charts", tags=["dashboard"], summary="Séries dos gráficos")
def dashboard_charts(hours: int = HOURS, ctx: Ctx = Depends(get_ctx)):
    return metrics.charts(ctx.db, ctx.now, ctx.cfg, hours)


@router.get("/dashboard/alerts", tags=["dashboard"], summary="Alertas calculados por regras")
def dashboard_alerts(ctx: Ctx = Depends(get_ctx)):
    return {"items": compute_alerts(ctx.db, ctx.now, ctx.cfg)}


# ------------------------------------------------------------------ activity
@router.get("/activity", tags=["activity"], summary="Histórico de atividades operacionais")
def activity(severity: Severity | None = None, entity_type: str | None = Query(None, max_length=24),
             page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), ctx: Ctx = Depends(get_ctx)):
    cond = [OperationalEvent.created_at <= ctx.now]
    if severity:
        cond.append(OperationalEvent.severity == severity)
    if entity_type:
        cond.append(OperationalEvent.entity_type == entity_type)
    total = ctx.db.scalar(select(func.count()).select_from(OperationalEvent).where(*cond))
    rows = ctx.db.scalars(select(OperationalEvent).where(*cond).order_by(OperationalEvent.created_at.desc())
                          .offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"id": str(e.id), "type": e.event_type, "severity": e.severity.value, "message": e.message,
         "entity_type": e.entity_type, "entity_id": e.entity_id, "actor": e.actor, "created_at": iso(e.created_at)}
        for e in rows]}


# ------------------------------------------------------------------ incidents
@router.get("/incidents", tags=["incidents"], summary="Lista ocorrências")
def list_incidents(status: IncidentStatus | None = None, priority: Priority | None = None, open_only: bool = False,
                   order: str | None = Query(None, max_length=64), ctx: Ctx = Depends(get_ctx)):
    rows = incident_svc.list_incidents(ctx.db, status=status, priority=priority, open_only=open_only, order_ref=order)
    return {"items": [incident_svc.incident_out(i) for i in rows], "total": len(rows)}


@router.post("/incidents", tags=["incidents"], status_code=201, summary="Cria uma ocorrência")
def create_incident(body: IncidentCreateIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(require_writer)):
    inc = incident_svc.create_incident(ctx.db, ctx.now, type=body.type, description=body.description, priority=body.priority,
                                       order_ref=body.order_ref, title=body.title, assignee=body.assignee, actor=user.email)
    ctx.db.commit()
    return incident_svc.incident_out(inc)


@router.get("/incidents/{incident_id}", tags=["incidents"], summary="Detalhe e histórico de alterações")
def get_incident(incident_id: str, ctx: Ctx = Depends(get_ctx)):
    inc = incident_svc.get_incident(ctx.db, incident_id)
    return {**incident_svc.incident_out(inc), "history": incident_svc.incident_history(ctx.db, inc)}


@router.patch("/incidents/{incident_id}", tags=["incidents"], summary="Atualiza status, prioridade, responsável ou resolução")
def update_incident(incident_id: str, body: IncidentUpdateIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(require_writer)):
    inc = incident_svc.get_incident(ctx.db, incident_id)
    incident_svc.update_incident(ctx.db, inc, ctx.now, user.email, **body.model_dump(exclude_unset=True))
    ctx.db.commit()
    return {**incident_svc.incident_out(inc), "history": incident_svc.incident_history(ctx.db, inc)}


# ------------------------------------------------------------------ reports
@router.get("/reports", tags=["reports"], summary="Tipos de relatório disponíveis")
def report_kinds():
    return {"items": [{"kind": k, "title": t} for k, t in reports.REPORT_KINDS.items()]}


def _kind(kind: str) -> str:
    return "general" if kind == "operational" else kind


@router.get("/reports/{kind}", tags=["reports"], summary="Gera um relatório (general|delays|restaurants|couriers|incidents)")
def get_report(kind: str, hours: int = HOURS, ctx: Ctx = Depends(get_ctx)):
    return reports.build_report(ctx.db, _kind(kind), ctx.now, ctx.cfg, hours)


@router.get("/reports/{kind}/export", tags=["reports"], summary="Exporta o relatório em CSV ou PDF")
def export_report(kind: str, format: str = Query("csv", pattern="^(csv|pdf)$"), hours: int = HOURS, ctx: Ctx = Depends(get_ctx)):
    rep = reports.build_report(ctx.db, _kind(kind), ctx.now, ctx.cfg, hours)
    name = f"opspilot-{rep['kind']}-{hours}h"
    if format == "pdf":
        return Response(reports.to_pdf(rep), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return Response(reports.to_csv(rep).encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


# ------------------------------------------------------------------ simulation
@router.get("/simulation/status", tags=["simulation"], summary="Estado do relógio e do cenário simulado")
def sim_status(ctx: Ctx = Depends(get_ctx)):
    return simulation.status(ctx.db)


@router.post("/simulation/advance", tags=["simulation"], summary="Avança o relógio simulado e processa pedidos")
def sim_advance(body: AdvanceIn, ctx: Ctx = Depends(get_ctx), _: User = Depends(require_writer)):
    return simulation.advance(ctx.db, body.minutes, ctx.cfg, body.auto_assign)


@router.post("/simulation/actions", tags=["simulation"], summary="Altera o cenário (demanda, entregadores, restaurantes...)")
def sim_action(body: SimActionIn, ctx: Ctx = Depends(get_ctx), _: User = Depends(require_writer)):
    db, a = ctx.db, body.action
    if a == "spawn_orders":
        return simulation.spawn_orders(db, body.count, body.restaurant)
    if a == "demand_spike":
        return simulation.demand_spike(db, max(body.count, 10))
    if a == "reduce_couriers":
        return simulation.reduce_couriers(db, body.count)
    if a == "restore_couriers":
        return simulation.restore_couriers(db)
    if a == "cancel_orders":
        return simulation.cancel_orders(db, body.count)
    if a == "generate_incidents":
        return simulation.generate_incidents(db, ctx.cfg)
    if not body.restaurant:
        from app.core.errors import AppError
        raise AppError("restaurant is required for restaurant_delay")
    return simulation.restaurant_delay(db, body.restaurant, body.factor)


@router.post("/simulation/reset", tags=["simulation"], summary="Restaura o ambiente de demonstração (admin)")
def sim_reset(ctx: Ctx = Depends(get_ctx), _: User = Depends(require_admin)):
    return seed.reset_demo(ctx.db)


# ------------------------------------------------------------------ settings
@router.get("/settings/rules", tags=["settings"], summary="Regras operacionais e limites ativos")
def rules(ctx: Ctx = Depends(get_ctx)):
    return {"rules": ctx.cfg.as_dict()}


@router.get("/settings/system", tags=["settings"], summary="Informações do ambiente")
def system_info(ctx: Ctx = Depends(get_ctx)):
    s = get_settings()
    return {"environment": s.environment, "database": ctx.db.bind.dialect.name, "simulated_data": True,
            "cors_origins": s.cors_origin_list, "token_expire_minutes": s.access_token_expire_minutes}
