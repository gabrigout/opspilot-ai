"""OpsPilot AI Copilot: the tool-calling loop.

receive -> screen -> [LLM -> tool_use -> validate -> execute -> tool_result]* -> answer -> persist
Bounded by max iterations, a wall-clock timeout and a per-turn tool-call budget.
"""
import re
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.providers import LLMProvider, ProviderError, build_provider
from app.agents.security import detect_blocked_request, rate_limiter, sanitize_value, wrap_tool_result
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import AgentConversation, AgentMessage, AgentToolExecution, Restaurant, User
from app.models.enums import ToolStatus, UserRole
from app.prompts.system import RECOMMENDATIONS_HEADING, SYSTEM_PROMPT
from app.rules import get_rule_config
from app.services import clock
from app.tools import REGISTRY, ToolContext, execute_tool

MAX_TOOL_CALLS_PER_TURN = 8
HISTORY_MESSAGES = 10
ORDER_CODE_RX = re.compile(r"ORD-\d{3,6}")


def get_provider(db: Session) -> tuple[LLMProvider, str | None]:
    names = list(db.scalars(select(Restaurant.name)))
    return build_provider(get_settings(), {"restaurants": names})


def provider_status(db: Session) -> dict:
    s = get_settings()
    provider, warning = get_provider(db)
    return {
        "mode": provider.mode, "provider": provider.name, "model": provider.model,
        "label": "Modo demonstrativo (sem LLM externo)" if provider.mode == "demo" else f"Conectado: {provider.name} / {provider.model}",
        "configuration_warning": warning,
        "tools": [{"name": t.name, "description": t.description, "mutates": t.mutates} for t in REGISTRY.values()],
        "limits": {"max_iterations": s.agent_max_iterations, "timeout_seconds": s.agent_timeout_seconds,
                   "messages_per_minute": s.agent_rate_limit_per_minute, "tool_calls_per_turn": MAX_TOOL_CALLS_PER_TURN},
    }


def split_recommendations(text: str) -> tuple[str, list[str]]:
    if RECOMMENDATIONS_HEADING not in text:
        return text.strip(), []
    answer, _, tail = text.partition(RECOMMENDATIONS_HEADING)
    recs = [re.sub(r"^[-*\d.\s]+", "", ln).strip() for ln in tail.splitlines() if ln.strip()]
    return answer.strip(), [r for r in recs if r]


def _persist_run(db: Session, conv: AgentConversation, run, now: datetime) -> AgentToolExecution:
    ex = AgentToolExecution(
        conversation_id=conv.id, tool_name=run.tool, arguments=run.arguments, result=sanitize_value(run.result) if run.result else None,
        status=run.status, error=run.error, duration_ms=run.duration_ms, created_at=now,
    )
    db.add(ex)
    db.flush()
    return ex


def _tool_payload(run) -> dict:
    return {"error": run.error} if run.status == ToolStatus.ERROR else run.result or {}


def chat(db: Session, user: User, message: str, conversation_id: uuid.UUID | None = None) -> dict:
    s = get_settings()
    rate_limiter.check(str(user.id), s.agent_rate_limit_per_minute)
    now = clock.now(db)
    provider, warning = get_provider(db)

    if conversation_id:
        conv = db.get(AgentConversation, conversation_id)
        if not conv or conv.user_id != user.id:
            raise NotFoundError("Conversation not found")
    else:
        conv = AgentConversation(user_id=user.id, title=message.strip()[:60], provider=provider.name, created_at=datetime.now(UTC))
        db.add(conv)
        db.flush()

    history = [{"role": m.role, "content": m.content} for m in conv.messages[-HISTORY_MESSAGES:]]
    user_msg = AgentMessage(conversation_id=conv.id, role="user", content=message, created_at=datetime.now(UTC))
    db.add(user_msg)
    db.flush()

    def finish(text: str, runs: list[dict], extra: dict | None = None) -> dict:
        answer, recs = split_recommendations(text)
        refs = sorted(set(ORDER_CODE_RX.findall(answer + " ".join(recs) + str(runs))))
        meta = {"provider": provider.name, "mode": provider.mode, "model": provider.model, "tool_runs": runs,
                "recommendations": recs, "order_refs": refs, **(extra or {})}
        a_msg = AgentMessage(conversation_id=conv.id, role="assistant", content=answer,
                             meta=sanitize_value(meta), created_at=datetime.now(UTC))
        db.add(a_msg)
        db.flush()
        for ex_id in meta.get("pending_execution_ids", []):
            ex = db.get(AgentToolExecution, uuid.UUID(ex_id))
            ex.message_id = a_msg.id
        db.commit()
        return {"conversation_id": str(conv.id), "message": message_out(a_msg), "configuration_warning": warning}

    blocked = detect_blocked_request(message)
    if blocked:
        return finish("Não posso atender a esse pedido: ele tenta contornar as regras do assistente (instruções, credenciais, SQL ou execução de código). "
                      "Posso ajudar com consultas operacionais sobre pedidos, entregadores, restaurantes e ocorrências.",
                      [], {"blocked": True, "reason": "unsafe_request"})

    messages: list[dict] = [*history, {"role": "user", "content": message}]
    tools = [t.to_anthropic() for t in REGISTRY.values()]
    ctx = ToolContext(db=db, now=now, cfg=get_rule_config(), actor=user.email, role=user.role)
    runs: list[dict] = []
    pending: list[str] = []
    deadline = time.monotonic() + s.agent_timeout_seconds
    total_calls = 0

    for _ in range(s.agent_max_iterations):
        if time.monotonic() > deadline:
            return finish("A consulta excedeu o tempo limite e foi interrompida. Tente uma pergunta mais específica.", runs,
                          {"error": "timeout", "pending_execution_ids": pending})
        try:
            resp = provider.complete(SYSTEM_PROMPT, messages, tools)
        except ProviderError as e:
            return finish("Não consegui obter resposta do provedor de IA agora. Os dados do sistema não foram alterados. "
                          "Tente novamente em instantes ou use o modo demonstrativo (remova ANTHROPIC_API_KEY).", runs,
                          {"error": "provider_error", "error_detail": str(e)[:200], "pending_execution_ids": pending})
        if not resp.tool_calls:
            return finish(resp.text or "Não encontrei dados suficientes para responder.", runs, {"pending_execution_ids": pending})

        blocks = ([{"type": "text", "text": resp.text}] if resp.text else []) + [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in resp.tool_calls]
        messages.append({"role": "assistant", "content": blocks})
        results = []
        for call in resp.tool_calls:
            total_calls += 1
            if total_calls > MAX_TOOL_CALLS_PER_TURN:
                payload = {"error": "Tool call budget for this turn exceeded"}
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": wrap_tool_result(call.name, payload)})
                continue
            run = execute_tool(call.name, call.input, ctx)
            ex = _persist_run(db, conv, run, datetime.now(UTC))
            if run.status == ToolStatus.PENDING_CONFIRMATION:
                pending.append(str(ex.id))
            rd = run.as_dict()
            rd["execution_id"] = str(ex.id)
            runs.append(rd)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": wrap_tool_result(call.name, _tool_payload(run))})
        messages.append({"role": "user", "content": results})

    return finish("Atingi o limite de iterações do agente sem concluir. Reformule a pergunta de forma mais específica.", runs,
                  {"error": "max_iterations", "pending_execution_ids": pending})


def confirm_action(db: Session, user: User, execution_id: uuid.UUID, approve: bool) -> dict:
    """Human-in-the-loop: only this endpoint can set `confirmed=True` for a mutating tool."""
    ex = db.get(AgentToolExecution, execution_id)
    if not ex or ex.status != ToolStatus.PENDING_CONFIRMATION:
        raise NotFoundError("No pending action found with this id")
    conv = db.get(AgentConversation, ex.conversation_id) if ex.conversation_id else None
    if conv and conv.user_id != user.id and user.role != UserRole.ADMIN:
        raise NotFoundError("No pending action found with this id")
    now = clock.now(db)
    if not approve:
        ex.status = ToolStatus.REJECTED
        text = "Ação cancelada: nada foi alterado."
        out = None
    else:
        ctx = ToolContext(db=db, now=now, cfg=get_rule_config(), actor=user.email, role=user.role, confirmed=True)
        run = execute_tool(ex.tool_name, ex.arguments, ctx)
        ex.status = ToolStatus.CONFIRMED if run.status == ToolStatus.SUCCESS else ToolStatus.ERROR
        ex.result, ex.error = (sanitize_value(run.result) if run.result else None), run.error
        out = run.result
        text = (f"Ocorrência **{run.result['code']}** criada com sucesso ({run.result['priority']})."
                if run.status == ToolStatus.SUCCESS else f"Não foi possível executar a ação: {run.error}")
    origin = db.get(AgentMessage, ex.message_id) if ex.message_id else None
    if origin and origin.meta:  # reflect the decision on the original message (survives reloads)
        meta = dict(origin.meta)
        meta["tool_runs"] = [{**r, "status": ex.status.value} if r.get("execution_id") == str(ex.id) else r
                             for r in meta.get("tool_runs", [])]
        origin.meta = meta
    if conv:
        db.add(AgentMessage(conversation_id=conv.id, role="assistant", content=text, created_at=datetime.now(UTC),
                            meta={"provider": "system", "mode": "confirmation", "tool_runs": [], "recommendations": [],
                                  "order_refs": ORDER_CODE_RX.findall(text), "confirmed_execution": str(ex.id)}))
    db.commit()
    return {"execution_id": str(ex.id), "status": ex.status.value, "message": text, "result": out}


def message_out(m: AgentMessage) -> dict:
    return {"id": str(m.id), "role": m.role, "content": m.content, "metadata": m.meta or {}, "created_at": m.created_at.isoformat()}


def conversation_out(c: AgentConversation, with_messages: bool = False) -> dict:
    d = {"id": str(c.id), "title": c.title, "provider": c.provider, "created_at": c.created_at.isoformat()}
    if with_messages:
        d["messages"] = [message_out(m) for m in c.messages]
    return d
