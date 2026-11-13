"""Simulated clock: real UTC time + a persisted offset the user can advance."""
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import SimulationState


def get_state(db: Session) -> SimulationState:
    state = db.get(SimulationState, 1)
    if state is None:
        state = SimulationState(id=1, offset_minutes=0.0, updated_at=datetime.now(UTC))
        db.add(state)
        db.flush()
    return state


def now(db: Session) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=get_state(db).offset_minutes)
