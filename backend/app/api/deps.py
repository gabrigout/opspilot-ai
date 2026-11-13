"""Shared FastAPI dependencies: DB session, auth, permissions, request context."""
import uuid
from dataclasses import dataclass
from datetime import datetime

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.models import User
from app.models.enums import UserRole
from app.rules import get_rule_config
from app.rules.engine import RuleConfig
from app.services import clock

bearer = HTTPBearer(auto_error=False, description="JWT obtido em POST /api/v1/auth/login")


def get_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> HTTPAuthorizationCredentials:
    if not creds:
        raise UnauthorizedError("Not authenticated")
    return creds


def current_user(creds: HTTPAuthorizationCredentials = Depends(get_token), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_token(creds.credentials)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise UnauthorizedError("Invalid or expired token") from None
    if not user or not user.is_active:
        raise UnauthorizedError("Invalid or expired token")
    return user


def require_writer(user: User = Depends(current_user)) -> User:
    if user.role not in (UserRole.ADMIN, UserRole.OPERATOR):
        raise ForbiddenError("Your role is read-only")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Administrator role required")
    return user


@dataclass
class Ctx:
    db: Session
    now: datetime
    cfg: RuleConfig


def get_ctx(db: Session = Depends(get_db)) -> Ctx:
    return Ctx(db=db, now=clock.now(db), cfg=get_rule_config())
