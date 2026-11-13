"""Demo provider: NO external LLM.

It speaks the same interface as a real LLM provider: first it maps the question to tool
calls by intent/pattern matching, then it renders an answer *only* from the tool results
it receives. It never pretends to be a language model.
"""
import json
import re
import unicodedata
from itertools import count

from app.agents.providers import LLMProvider, ProviderResponse, ToolCall
from app.prompts.system import RECOMMENDATIONS_HEADING

_ids = count(1)
ORDER_RX = re.compile(r"(?:ord[- ]?|#)\s*(\d{3,6})", re.I)
RESULT_RX = re.compile(r'<tool_data tool="([^"]+)">(.*)</tool_data>', re.S)


def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _has(q: str, *words: str) -> bool:
    return any(w in q for w in words)


class DemoProvider(LLMProvider):
    name = "demo"
    mode = "demo"
    model = None

    def __init__(self, hints: dict | None = None):
        self.restaurants: list[str] = (hints or {}).get("restaurants", [])

    # ---------------------------------------------------------------- interface
    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> ProviderResponse:
        question, results = self._split(messages)
        if not results:
            calls = self.plan(question)
            if calls:
                return ProviderResponse("", calls)
            return ProviderResponse(self.help_text())
        return ProviderResponse(self.compose(results))

    @staticmethod
    def _split(messages: list[dict]) -> tuple[str, list[tuple[str, dict, dict]]]:
        """Return (latest user question, [(tool, args, result)]) for the current turn."""
        last_q = ""
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if m["role"] == "user" and isinstance(m["content"], str):
                last_q = m["content"]
                break
        else:
            i = 0
        calls: dict[str, tuple[str, dict]] = {}
        out = []
        for m in messages[i + 1:]:
            if not isinstance(m["content"], list):
                continue
            for b in m["content"]:
                if b.get("type") == "tool_use":
                    calls[b["id"]] = (b["name"], b["input"])
                elif b.get("type") == "tool_result":
                    name, args = calls.get(b["tool_use_id"], ("?", {}))
                    match = RESULT_RX.search(b["content"])
                    out.append((name, args, json.loads(match.group(2)) if match else {}))
        return last_q, out

    # ---------------------------------------------------------------- planning
    def plan(self, question: str) -> list[ToolCall]:
        q = plain(question)
        m = ORDER_RX.search(question)
        code = f"ORD-{m.group(1)}" if m else None

        def call(name: str, **kw) -> ToolCall:
            return ToolCall(f"demo_{next(_ids)}", name, kw)

        if _has(q, "abr", "cri", "registr") and "ocorrenc" in q:
            desc = question.split(":", 1)[1].strip() if ":" in question else question.strip()
            typ = ("DELIVERY_DELAY" if _has(q, "atras") else "CUSTOMER_COMPLAINT" if _has(q, "reclam")
                   else "ADDRESS_ISSUE" if _has(q, "endere") else "COURIER_ISSUE" if _has(q, "entregador")
                   else "SLOW_PREPARATION" if _has(q, "prepar", "cozinha") else "ORDER_NOT_FOUND" if _has(q, "localiz")
                   else "COURIER_SHORTAGE" if _has(q, "falta") else "DELIVERY_DELAY")
            prio = ("CRITICAL" if _has(q, "critic") else "HIGH" if _has(q, "alta", "urgente")
                    else "LOW" if _has(q, "baixa") else "MEDIUM")
            args = {"type": typ, "description": desc if len(desc) >= 10 else f"Ocorrência registrada via Copilot: {desc}".ljust(10),
                    "priority": prio}
            if code:
                args["order_code"] = code
            return [call("create_incident", **args)]
        if code and _has(q, "recomend", "sugir", "melhor entregador", "quem deve", "atribu"):
            return [call("recommend_courier", order_code=code)]
        if code and _has(q, "histor", "linha do tempo", "eventos"):
            return [call("get_order_history", order_code=code)]
        if code:
            return [call("get_order", order_code=code)]
        if _has(q, "relat"):
            kind = ("delays" if _has(q, "atras") else "restaurants" if _has(q, "restaurante")
                    else "couriers" if _has(q, "entregador") else "incidents" if _has(q, "ocorrenc") else "general")
            return [call("generate_operational_report", kind=kind)]
        if _has(q, "risco"):
            return [call("get_at_risk_orders", limit=15)]
        if _has(q, "atras"):
            return [call("get_delayed_orders", limit=15)]
        named = next((r for r in self.restaurants if plain(r) in q), None)
        if named:
            return [call("get_restaurant_performance", restaurant=named)]
        if _has(q, "restaurante", "cozinha"):
            return [call("generate_operational_report", kind="restaurants")]
        if _has(q, "entregador", "motoboy", "courier"):
            return [call("get_available_couriers", limit=10)]
        if "ocorrenc" in q:
            return [call("get_open_incidents", limit=10)]
        if _has(q, "como esta", "operacao", "resumo", "visao geral", "indicador", "metrica", "hoje", "panorama"):
            return [call("get_operational_metrics", period_hours=24), call("get_delayed_orders", limit=5),
                    call("get_at_risk_orders", limit=5), call("get_open_incidents", limit=5)]
        for word, status in (("cancelad", "CANCELLED"), ("entregue", "DELIVERED"), ("em entrega", "IN_DELIVERY"),
                             ("aguardando entregador", "WAITING_COURIER"), ("preparo", "PREPARING"), ("recebid", "RECEIVED")):
            if word in q:
                return [call("search_orders", status=status, limit=10)]
        if _has(q, "pedido"):
            return [call("search_orders", limit=10)]
        return []

    def help_text(self) -> str:
        return ("Estou em **modo demonstrativo** (sem LLM externo) e não identifiquei uma consulta para essa pergunta. "
                "Posso consultar, por exemplo:\n- pedidos atrasados ou com risco de atraso\n- o panorama geral da operação\n"
                "- entregadores disponíveis\n- restaurantes com problemas\n- um pedido específico (ex.: *ORD-1042*), seu histórico ou "
                "uma recomendação de entregador\n- ocorrências abertas\n- um relatório operacional\n"
                "- abrir uma ocorrência (ex.: *abra uma ocorrência de atraso para ORD-1042: cliente aguardando há 40 min*)")

    # ---------------------------------------------------------------- composing
    def compose(self, results: list[tuple[str, dict, dict]]) -> str:
        facts: list[str] = []
        recs: list[str] = []
        for tool, args, res in results:
            if set(res) == {"error"}:
                facts.append(f"Não foi possível executar `{tool}`: {res['error']}")
                continue
            fn = getattr(self, f"_r_{tool}", None)
            if fn is None:
                facts.append(f"Ferramenta `{tool}` executada.")
                continue
            f, r = fn(args, res)
            facts.append(f)
            recs.extend(r)
        text = "\n\n".join(facts)
        if recs:
            text += f"\n\n{RECOMMENDATIONS_HEADING}\n" + "\n".join(f"- {r}" for r in dict.fromkeys(recs))
        return text

    @staticmethod
    def _err(res: dict) -> str | None:
        return res.get("error")

    def _r_get_operational_metrics(self, a, r):
        avg = r["avg_delivery_minutes"]
        return (f"**Panorama operacional (últimas {r['period_hours']}h)**\n"
                f"- Pedidos: {r['total_orders']} · entregues: {r['delivered']} · cancelados: {r['cancelled']}\n"
                f"- Em andamento: {r['in_progress']} (atrasados: {r['delayed']}, em risco: {r['at_risk']}, sem entregador: {r['waiting_courier']})\n"
                f"- Tempo médio de entrega: {f'{avg} min' if avg is not None else 'sem entregas no período'}\n"
                f"- Entregadores disponíveis: {r['available_couriers']} de {r['total_couriers']}\n"
                f"- Ocorrências abertas: {r['open_incidents']}"), []

    def _r_get_delayed_orders(self, a, r):
        if not r["total_delayed"]:
            return "**Pedidos atrasados:** nenhum pedido está atrasado no momento.", []
        lines = [f"- **{o['code']}** · {o['restaurant']} · {o['delay_minutes']:.0f} min de atraso · prioridade {o['delay_priority']} · "
                 f"{o['status']} · {'entregador ' + o['courier'] if o['courier'] else 'sem entregador'}" for o in r["orders"]]
        recs = []
        worst = [o["code"] for o in r["orders"] if o["delay_priority"] in ("CRITICAL", "HIGH")]
        if worst:
            recs.append(f"Priorizar contato com os clientes e abrir ocorrência para: {', '.join(worst[:5])}.")
        nocour = [o["code"] for o in r["orders"] if not o["courier"]]
        if nocour:
            recs.append(f"Atribuir entregador imediatamente a: {', '.join(nocour[:5])}.")
        return f"**{r['total_delayed']} pedido(s) atrasado(s)** (mostrando {len(r['orders'])}):\n" + "\n".join(lines), recs

    def _r_get_at_risk_orders(self, a, r):
        if not r["total_at_risk"]:
            return "**Risco de atraso:** nenhum pedido em risco pelas regras atuais.", []
        lines = [f"- **{o['code']}** · {o['restaurant']} · {o['status']} · restam {o['remaining_minutes']:.0f} min\n  - " +
                 "\n  - ".join(o["risk_reasons"]) for o in r["orders"]]
        recs = ["Antecipar a atribuição de entregador e acompanhar o preparo dos pedidos em risco."]
        return f"**{r['total_at_risk']} pedido(s) com risco de atraso:**\n" + "\n".join(lines), recs

    def _r_get_available_couriers(self, a, r):
        names = ", ".join(f"{c['code']}" for c in r["couriers"])
        recs = []
        if r["available_count"] == 0:
            recs.append("Sem entregadores disponíveis: acionar entregadores offline ou pausar novos pedidos.")
        elif r["available_count"] <= 3:
            recs.append("Capacidade baixa: considere acionar entregadores offline.")
        by = ", ".join(f"{k}: {v}" for k, v in r["by_status"].items())
        return (f"**{r['available_count']} entregador(es) disponível(is)** de {r['total_couriers']} ({by}).\n"
                + (f"Disponíveis: {names}." if names else "")), recs

    def _r_recommend_courier(self, a, r):
        if self._err(r) or not r.get("candidates"):
            return f"**Recomendação para {r.get('order_code', a.get('order_code'))}:** nenhum entregador elegível encontrado.", ["Acionar entregadores offline ou aguardar liberação."]
        lines = [f"{i}. **{c['courier']['code']}** ({c['courier']['name']}) · score {c['score']} · {c['distance_km']} km · "
                 f"{c['courier']['active_orders']} pedido(s) ativo(s)" for i, c in enumerate(r["candidates"], 1)]
        top = r["candidates"][0]["courier"]["code"]
        return (f"**Ranking de entregadores para {r['order_code']}** ({r['restaurant']}) – {r['total_eligible']} elegíveis:\n" + "\n".join(lines),
                [f"Considere atribuir {top} (melhor score). A atribuição não é automática e exige aprovação humana na página do pedido."])

    def _r_get_restaurant_performance(self, a, r):
        recs = []
        if r["prep_alert"]:
            recs.append(f"{r['name']}: preparo {r['prep_alert_pct']:.0f}% acima da média; contatar o restaurante e avaliar pausa temporária.")
        cmp = f"{r['vs_operation_avg_pct']:+.0f}% vs média da operação" if r["vs_operation_avg_pct"] is not None else "sem base de comparação"
        return (f"**{r['name']}** ({r['code']}, {r['status']}) – últimas {r['period_hours']}h\n"
                f"- Pedidos: {r['orders']} · cancelados: {r['cancelled']} ({r['cancellation_rate']}%) · atrasados: {r['delayed_orders']}\n"
                f"- Preparo médio: {r['avg_prep_minutes'] if r['avg_prep_minutes'] is not None else '—'} min ({cmp}; média da operação: {r['operation_avg_prep_minutes']} min)"), recs

    def _r_generate_operational_report(self, a, r):
        parts = [f"**{r['title']}** (últimas {r['period']['hours']}h, dados simulados)", r["summary"]]
        parts.append("\n".join(f"- {i['label']}: {i['value']}" for i in r["indicators"]))
        if r["problems"]:
            parts.append("**Principais problemas**\n" + "\n".join(f"- {p}" for p in r["problems"][:8]))
        parts.append("O relatório completo (com exportação CSV/PDF) está na página *Relatórios*.")
        return "\n\n".join(parts), r["recommendations"]

    def _r_get_open_incidents(self, a, r):
        if not r["total_open"]:
            return "**Ocorrências abertas:** nenhuma.", []
        lines = [f"- **{i['code']}** · {i['priority']} · {i['title']} · {i['status']}"
                 + (f" · pedido {i['order']['code']}" if i["order"] else "") + (f" · resp.: {i['assignee']}" if i["assignee"] else " · sem responsável")
                 for i in r["incidents"]]
        pr = ", ".join(f"{k}: {v}" for k, v in r["by_priority"].items())
        recs = []
        if any(not i["assignee"] for i in r["incidents"]):
            recs.append("Designar responsável às ocorrências abertas sem responsável.")
        return f"**{r['total_open']} ocorrência(s) aberta(s)** ({pr}):\n" + "\n".join(lines), recs

    def _r_get_order(self, a, r):
        if self._err(r):
            return f"Não consegui consultar o pedido: {r['error']}", []
        itens = ", ".join(f"{i['quantity']}x {i['name']}" for i in r["items"])
        recs = []
        if r["is_delayed"]:
            recs.append(f"{r['code']} está atrasado ({r['delay_minutes']:.0f} min): avaliar contato com o cliente e abertura de ocorrência.")
        elif r["at_risk"]:
            recs.append(f"{r['code']} está em risco: " + "; ".join(r["risk_reasons"]) + ".")
        if not r["courier"] and r["status"] in ("READY_FOR_PICKUP", "WAITING_COURIER", "PREPARING", "CONFIRMED"):
            recs.append(f"Pedir recomendação de entregador para {r['code']}.")
        return (f"**Pedido {r['code']}** – {r['status']} ({r['situation']})\n"
                f"- Restaurante: {r['restaurant']['name']} · cliente fictício: {r['customer']['name']}\n"
                f"- Entregador: {r['courier']['code'] + ' – ' + r['courier']['name'] if r['courier'] else 'não atribuído'}\n"
                f"- Itens: {itens} · total R$ {r['total_amount']:.2f}\n"
                f"- Prazo: {r['promised_at']} ({'atrasado ' + format(r['delay_minutes'], '.0f') + ' min' if r['is_delayed'] else 'restam ' + format(r['remaining_minutes'] or 0, '.0f') + ' min'})"), recs

    def _r_get_order_history(self, a, r):
        if self._err(r):
            return f"Não consegui consultar o histórico: {r['error']}", []
        lines = [f"- {e['created_at']} · {e['message']} ({e['actor']})" for e in r["events"]]
        return f"**Histórico de {r['order_code']}** (status atual: {r['current_status']}):\n" + "\n".join(lines), []

    def _r_search_orders(self, a, r):
        if not r["total_found"]:
            return "Nenhum pedido encontrado para esse filtro.", []
        lines = [f"- **{o['code']}** · {o['restaurant']} · {o['status']} · {o['situation']}" for o in r["orders"]]
        by = ", ".join(f"{k}: {v}" for k, v in r["by_status"].items())
        return f"**{r['total_found']} pedido(s) encontrado(s)** ({by}); mostrando {r['returned']}:\n" + "\n".join(lines), []

    def _r_create_incident(self, a, r):
        if r.get("requires_confirmation"):
            p = r["proposal"]
            return (f"Preparei a ocorrência abaixo, mas **ela ainda não foi criada**. Confirme na interface para registrá-la:\n"
                    f"- Tipo: {p['type']} · Prioridade: {p['priority']}" + (f" · Pedido: {p['order_code']}" if p.get("order_code") else "") +
                    f"\n- Descrição: {p['description']}"), []
        if self._err(r):
            return f"Não foi possível criar a ocorrência: {r['error']}", []
        return f"Ocorrência **{r['code']}** criada ({r['priority']}).", []
