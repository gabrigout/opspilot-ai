"""Operational event log (activity feed + incident history)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OperationalEvent
from app.models.enums import Severity


def log_event(
    db: Session,
    when: datetime,
    event_type: str,
    message: str,
    severity: Severity = Severity.INFO,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict | None = None,
    actor: str = "system",
) -> OperationalEvent:
    ev = OperationalEvent(
        event_type=event_type, severity=severity, message=message, entity_type=entity_type,
        entity_id=entity_id, payload=payload, actor=actor, created_at=when,
    )
    db.add(ev)
    return ev


def recent_events(db: Session, limit: int = 20, before: datetime | None = None) -> list[OperationalEvent]:
    stmt = select(OperationalEvent).order_by(OperationalEvent.created_at.desc())
    if before:
        stmt = stmt.where(OperationalEvent.created_at <= before)
    return list(db.scalars(stmt.limit(limit)))
