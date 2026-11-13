"""Password hashing and JWT helpers."""
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> tuple[str, int]:
    s = get_settings()
    expires = timedelta(minutes=s.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "jti": uuid.uuid4().hex,
               "exp": datetime.now(UTC) + expires, "iat": datetime.now(UTC)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM), int(expires.total_seconds())


# In-memory revocation list: logout invalidates the token until the process restarts
# (documented limitation; use Redis or a DB table for multi-instance deployments).
_revoked: set[str] = set()


def revoke(jti: str) -> None:
    _revoked.add(jti)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired/revoked tokens."""
    payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    if payload.get("jti") in _revoked:
        raise jwt.InvalidTokenError("revoked")
    return payload
