import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import copilot
from app.api.deps import current_user
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.models import AgentConversation, User
from app.schemas.inputs import ChatIn, ConfirmIn

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(current_user)])


@router.get("/status", summary="Modo do agente (demonstrativo ou provedor conectado), ferramentas e limites")
def status(db: Session = Depends(get_db)):
    return copilot.provider_status(db)


@router.post("/chat", summary="Envia uma mensagem ao Copilot (executa o ciclo de tool calling)")
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return copilot.chat(db, user, body.message, body.conversation_id)


@router.get("/conversations", summary="Conversas do usuário")
def conversations(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(AgentConversation).where(AgentConversation.user_id == user.id)
                      .order_by(AgentConversation.created_at.desc()).limit(50))
    return {"items": [copilot.conversation_out(c) for c in rows]}


@router.get("/conversations/{conversation_id}", summary="Mensagens de uma conversa")
def conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(AgentConversation, conversation_id)
    if not c or c.user_id != user.id:
        raise NotFoundError("Conversation not found")
    return copilot.conversation_out(c, with_messages=True)


@router.post("/executions/{execution_id}/confirm", summary="Confirma ou rejeita uma ação proposta pelo agente")
def confirm(execution_id: uuid.UUID, body: ConfirmIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return copilot.confirm_action(db, user, execution_id, body.approve)
