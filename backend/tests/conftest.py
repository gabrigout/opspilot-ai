import os

# Must be set before the app is imported: in-memory SQLite, deterministic settings, no external AI.
os.environ.update(
    ENVIRONMENT="test", DATABASE_URL="sqlite://", SECRET_KEY="test-secret-key-with-more-than-32-characters!!",
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
    Base.metadata.create_all(engine)


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
