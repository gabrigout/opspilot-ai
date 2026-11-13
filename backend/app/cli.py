"""Maintenance commands:  python -m app.cli reset | seed | create-admin <email>"""
import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import Restaurant, User
from app.models.enums import UserRole
from app.services import seed


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if get_settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if cmd == "reset":
            print("Restored demo data:", seed.reset_demo(db))
        elif cmd == "seed":
            seed.ensure_users(db)
            if db.scalars(select(Restaurant).limit(1)).first():
                print("Data already present; use 'reset' to rebuild the demo dataset.")
            else:
                print("Seeded:", seed.seed_demo(db))
            db.commit()
        elif cmd == "create-admin" and len(argv) > 2:
            password = getpass.getpass("Password (min 12 chars): ")
            if len(password) < 12:
                print("Password too short.")
                return 1
            db.add(User(email=argv[2].lower(), full_name="Administrador", hashed_password=hash_password(password),
                        role=UserRole.ADMIN, created_at=datetime.now(UTC)))
            db.commit()
            print("Admin created.")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
