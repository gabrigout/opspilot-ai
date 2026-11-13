"""Operational reports (computed in the backend) with CSV / PDF export."""
import csv
import io
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.enums import PRIORITY_RANK, Priority
from app.rules.engine import RuleConfig
from app.services import couriers as courier_svc
from app.services import incidents as incident_svc
from app.services import metrics
from app.services.alerts import compute_alerts
from app.services.orders import active_orders, iso
from app.services.restaurants import restaurant_stats

REPORT_KINDS = {
    "general": "Relatório geral",
    "delays": "Relatório de atrasos",
    "restaurants": "Relatório de desempenho dos restaurantes",
    "couriers": "Relatório de entregadores",
    "incidents": "Relatório de ocorrências",
}


def _fmt(v) -> str:
    return "—" if v is None else str(v)


def build_report(db: Session, kind: str, now: datetime, cfg: RuleConfig, hours: int = 24) -> dict:
    if kind not in REPORT_KINDS:
        raise NotFoundError(f"Unknown report '{kind}'. Available: {', '.join(REPORT_KINDS)}")
    k = metrics.kpis(db, now, cfg, hours)
    report = {
        "kind": kind, "title": REPORT_KINDS[kind], "generated_at": iso(now), "simulated_data": True,
        "period": {"hours": hours, "from": iso(now - timedelta(hours=hours)), "to": iso(now)},
        "indicators": [], "summary": "", "problems": [], "recommendations": [], "table": {"columns": [], "rows": []},
    }
    alerts = [a for a in compute_alerts(db, now, cfg) if a["level"] != "INFO"]
    builder = {"general": _general, "delays": _delays, "restaurants": _restaurants,
               "couriers": _couriers, "incidents": _incidents}[kind]
    builder(db, now, cfg, hours, k, alerts, report)
    return report


def _general(db, now, cfg, hours, k, alerts, r):
    r["indicators"] = [
        {"label": "Pedidos no período", "value": k["total_orders"]}, {"label": "Em andamento", "value": k["in_progress"]},
        {"label": "Entregues", "value": k["delivered"]}, {"label": "Atrasados", "value": k["delayed"]},
        {"label": "Em risco", "value": k["at_risk"]}, {"label": "Cancelados", "value": k["cancelled"]},
        {"label": "Tempo médio de entrega (min)", "value": _fmt(k["avg_delivery_minutes"])},
        {"label": "Entregadores disponíveis", "value": f"{k['available_couriers']}/{k['total_couriers']}"},
        {"label": "Ocorrências abertas", "value": k["open_incidents"]},
    ]
    rate = round(k["cancelled"] / k["total_orders"] * 100, 1) if k["total_orders"] else 0
    r["summary"] = (f"Nas últimas {hours}h foram registrados {k['total_orders']} pedidos, com {k['delivered']} entregues, "
                    f"{k['cancelled']} cancelados ({rate}%). Agora há {k['in_progress']} em andamento, "
                    f"dos quais {k['delayed']} atrasados e {k['at_risk']} em risco.")
    r["problems"] = [f"{a['title']}: {a['message']}" for a in alerts]
    r["recommendations"] = _recommendations(k, alerts)
    r["table"] = {"columns": ["Indicador", "Valor"], "rows": [[i["label"], i["value"]] for i in r["indicators"]]}


def _recommendations(k, alerts) -> list[str]:
    rules = {a["rule"] for a in alerts}
    recs = []
    if "ORDERS_WITHOUT_COURIER" in rules or "CAPACITY_NO_COURIERS" in rules or "CAPACITY_INSUFFICIENT" in rules:
        recs.append("Atribuir entregadores aos pedidos aguardando retirada, priorizando os mais próximos do prazo (veja a recomendação por pedido).")
    if "ORDERS_DELAYED" in rules:
        recs.append("Contatar clientes dos pedidos atrasados e abrir ocorrências para os de prioridade ALTA ou CRÍTICA.")
    if "ORDERS_AT_RISK" in rules:
        recs.append("Monitorar de perto os pedidos em risco e antecipar a atribuição de entregador.")
    if any(x.startswith("RESTAURANT_SLOW_PREP") or x == "RESTAURANT_SLOW_PREP" for x in rules):
        recs.append("Conversar com os restaurantes com preparo acima da média e avaliar pausar temporariamente novos pedidos.")
    if any(x.startswith("INCIDENT_STALE") for x in rules):
        recs.append("Escalar ocorrências críticas abertas há muito tempo para um responsável.")
    return recs or ["Nenhuma ação corretiva necessária: manter o monitoramento."]


def _delays(db, now, cfg, hours, k, alerts, r):
    rows = []
    for o, a in sorted(active_orders(db, now, cfg), key=lambda t: -t[1].delay_minutes):
        if a.is_delayed:
            rows.append([o.code, o.restaurant.name, o.status.value, f"{a.delay_minutes:.0f}", a.priority.value,
                         o.courier.code if o.courier else "—"])
    risk = [(o, a) for o, a in active_orders(db, now, cfg) if a.at_risk]
    r["indicators"] = [{"label": "Pedidos atrasados", "value": len(rows)}, {"label": "Pedidos em risco", "value": len(risk)},
                       {"label": "Atraso máximo (min)", "value": max([float(x[3]) for x in rows], default=0)}]
    r["summary"] = f"{len(rows)} pedido(s) atrasado(s) e {len(risk)} em risco no momento."
    r["problems"] = [f"{o.code}: {'; '.join(a.risk_reasons)}" for o, a in risk] + [
        f"{x[0]} ({x[1]}) atrasado {x[3]} min – prioridade {x[4]}" for x in rows if x[4] in ("HIGH", "CRITICAL")]
    r["recommendations"] = _recommendations(k, alerts)
    r["table"] = {"columns": ["Pedido", "Restaurante", "Status", "Atraso (min)", "Prioridade", "Entregador"], "rows": rows}


def _restaurants(db, now, cfg, hours, k, alerts, r):
    st = restaurant_stats(db, now, cfg, hours)
    rows = [[x["code"], x["name"], x["orders"], _fmt(x["avg_prep_minutes"]), _fmt(x["vs_operation_avg_pct"]),
             f"{x['cancellation_rate']}%", x["delayed_orders"], x["rating"]]
            for x in sorted(st["restaurants"], key=lambda x: -x["orders"])]
    slow = [x for x in st["restaurants"] if x["prep_alert"]]
    r["indicators"] = [{"label": "Restaurantes", "value": len(st["restaurants"])},
                       {"label": "Preparo médio da operação (min)", "value": _fmt(st["operation_avg_prep_minutes"])},
                       {"label": "Restaurantes com preparo acima da média", "value": len(slow)}]
    r["summary"] = f"{len(slow)} restaurante(s) com preparo ≥ {int((cfg.restaurant_prep_factor - 1) * 100)}% acima da média operacional."
    r["problems"] = [f"{x['name']}: preparo {x['prep_alert_pct']:.0f}% acima da média ({x['avg_prep_minutes']} min)" for x in slow]
    r["recommendations"] = [f"Revisar capacidade da cozinha de {x['name']} e considerar pausa temporária." for x in slow] or ["Sem restaurantes críticos."]
    r["table"] = {"columns": ["Código", "Restaurante", "Pedidos", "Preparo médio (min)", "vs média (%)", "Cancelamento", "Atrasados", "Avaliação"], "rows": rows}


def _couriers(db, now, cfg, hours, k, alerts, r):
    cs = courier_svc.list_couriers(db, now)
    by = {}
    for c in cs:
        by[c["status"]] = by.get(c["status"], 0) + 1
    r["indicators"] = [{"label": s.title(), "value": n} for s, n in sorted(by.items())] + [
        {"label": "Total", "value": len(cs)}]
    r["summary"] = f"{by.get('AVAILABLE', 0)} de {len(cs)} entregadores estão disponíveis."
    r["problems"] = [a["message"] for a in alerts if a["rule"].startswith(("CAPACITY", "ORDERS_WITHOUT"))]
    r["recommendations"] = _recommendations(k, alerts)
    r["table"] = {"columns": ["Código", "Nome", "Status", "Pedidos ativos", "Entregas", "Tempo médio (min)"],
                  "rows": [[c["code"], c["name"], c["status"], c["active_orders"], c["total_deliveries"], c["avg_delivery_minutes"]] for c in cs]}


def _incidents(db, now, cfg, hours, k, alerts, r):
    all_inc = incident_svc.list_incidents(db)
    open_ = [i for i in all_inc if i.status.value in ("OPEN", "INVESTIGATING", "WAITING_ACTION")]
    crit = [i for i in open_ if i.priority in (Priority.CRITICAL, Priority.HIGH)]
    r["indicators"] = [{"label": "Total de ocorrências", "value": len(all_inc)}, {"label": "Abertas", "value": len(open_)},
                       {"label": "Alta/Crítica abertas", "value": len(crit)}]
    r["summary"] = f"{len(open_)} ocorrência(s) aberta(s), {len(crit)} com prioridade alta ou crítica."
    r["problems"] = [f"{i.code} ({i.priority.value}): {i.title}" for i in sorted(crit, key=lambda i: -PRIORITY_RANK[i.priority])]
    r["recommendations"] = (["Designar responsável às ocorrências abertas sem responsável."]
                            if any(not i.assignee for i in open_) else ["Todas as ocorrências abertas têm responsável."])
    r["table"] = {"columns": ["Código", "Tipo", "Prioridade", "Status", "Pedido", "Responsável"],
                  "rows": [[i.code, i.type.value, i.priority.value, i.status.value, i.order.code if i.order else "—", i.assignee or "—"] for i in all_inc]}


def to_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([report["title"]])
    w.writerow(["Gerado em", report["generated_at"], "Período (h)", report["period"]["hours"], "Dados simulados"])
    w.writerow([])
    for i in report["indicators"]:
        w.writerow([i["label"], i["value"]])
    w.writerow([])
    w.writerow(report["table"]["columns"])
    w.writerows(report["table"]["rows"])
    return buf.getvalue()


def to_pdf(report: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=report["title"], leftMargin=28, rightMargin=28)
    ss = getSampleStyleSheet()
    els = [Paragraph(f"OpsPilot AI — {report['title']}", ss["Title"]),
           Paragraph(f"Gerado em {report['generated_at']} · período: últimas {report['period']['hours']}h · dados simulados", ss["Normal"]),
           Spacer(1, 10), Paragraph("Resumo", ss["Heading2"]), Paragraph(report["summary"], ss["Normal"])]

    def table(data, head=True):
        t = Table([[Paragraph(str(c), ss["BodyText"]) for c in row] for row in data], repeatRows=1 if head else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if head:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E7FF")))
        t.setStyle(TableStyle(style))
        return t

    els += [Spacer(1, 8), Paragraph("Indicadores", ss["Heading2"]),
            table([[i["label"], i["value"]] for i in report["indicators"]], head=False)]
    if report["problems"]:
        els += [Paragraph("Principais problemas", ss["Heading2"])] + [Paragraph(f"• {p}", ss["Normal"]) for p in report["problems"]]
    els += [Paragraph("Recomendações", ss["Heading2"])] + [Paragraph(f"• {p}", ss["Normal"]) for p in report["recommendations"]]
    if report["table"]["rows"]:
        els += [Spacer(1, 8), Paragraph("Detalhamento", ss["Heading2"]), table([report["table"]["columns"], *report["table"]["rows"]])]
    doc.build(els)
    return buf.getvalue()
