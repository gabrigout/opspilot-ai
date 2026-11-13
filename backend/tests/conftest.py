import os

# Must be set before the app is imported: in-memory SQLite, deterministic settings, no external AI.
# TEST_DATABASE_URL (e.g. postgresql+psycopg://user:pw@localhost/opspilot_test) runs the whole suite on
# PostgreSQL with the schema created by the Alembic migrations; the default is in-memory SQLite.
os.environ.update(
    ENVIRONMENT="test", DATABASE_URL=os.environ.get("TEST_DATABASE_URL", "sqlite://"),
    SECRET_KEY="test-secret-key-with-more-than-32-characters!!",
    AI_PROVIDER="demo", ANTHROPIC_API_KEY="", RULES_OVERRIDES="{}",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.security import rate_limiter  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _tables():
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
        return
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")  # start from a clean schema, then prove the migration builds it
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def db():
    """Fresh deterministic demo dataset for every test."""
    rate_limiter.reset()
    with SessionLocal() as session:
        seed.reset_demo(session)
        yield session


@pytest.fixture
def client(db):
    return TestClient(app)


def login(client: TestClient, email="admin@opspilot.local", password="opspilot-demo") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return login(client)


@pytest.fixture
def viewer_auth(client):
    return login(client, "viewer@opspilot.local")
