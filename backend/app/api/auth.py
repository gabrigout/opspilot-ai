from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.security import rate_limiter
from app.api.deps import current_user, get_token
from app.core.db import get_db
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token, decode_token, hash_password, revoke, verify_password
from app.models import User
from app.schemas.inputs import LoginIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH = hash_password("not-a-real-password")  # keeps timing similar for unknown users


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": u.role.value}


@router.post("/login", response_model=TokenOut, summary="Autentica e devolve um JWT com expiração")
def login(body: LoginIn, db: Session = Depends(get_db)):
    rate_limiter.check(f"login:{body.email.lower()}", 10)
    user = db.scalars(select(User).where(User.email == body.email.lower())).first()
    ok = verify_password(body.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        raise UnauthorizedError("Invalid email or password")
    token, expires = create_access_token(str(user.id), user.role.value)
    return TokenOut(access_token=token, expires_in=expires, user=user_out(user))


@router.post("/logout", status_code=204, summary="Revoga o token atual")
def logout(creds: HTTPAuthorizationCredentials = Depends(get_token), _: User = Depends(current_user)):
    revoke(decode_token(creds.credentials)["jti"])


@router.get("/me", summary="Usuário autenticado")
def me(user: User = Depends(current_user)):
    return user_out(user)
