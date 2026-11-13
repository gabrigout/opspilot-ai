"""Production safety checks and HTTP hardening."""
import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SQLITE_URL, Settings
from app.models import User
from app.services import seed

GOOD = dict(environment="production", secret_key="x" * 40, database_url="postgresql+psycopg://u:p@h/db")


def test_production_accepts_strong_config():
    assert Settings(**GOOD).is_production


@pytest.mark.parametrize("override", [
    {"secret_key": "short"},
    {"secret_key": "dev-secret-change-me-dev-secret-change-me"},
    {"database_url": "sqlite:///./x.db"},
    {"admin_password": "short"},
])
def test_production_rejects_weak_config(override):
    with pytest.raises(ValidationError):
        Settings(**{**GOOD, **override})


def test_demo_mode_allows_sqlite_but_still_requires_a_real_secret():
    ok = Settings(environment="demo", secret_key="y" * 40, database_url="sqlite:////tmp/opspilot.db")
    assert ok.is_demo and not ok.is_production
    for bad in ("short", "dev-secret-change-me-dev-secret-change-me"):
        with pytest.raises(ValidationError):
            Settings(environment="demo", secret_key=bad, database_url="sqlite:////tmp/opspilot.db")


def test_on_vercel_defaults_are_safe(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    # no secret configured -> refuses to start instead of serving with the public dev key
    with pytest.raises(ValidationError):
        Settings(environment="development", secret_key="dev-secret-change-me-dev-secret-change-me")
    s = Settings(environment="development", secret_key="z" * 40, database_url=DEFAULT_SQLITE_URL)
    assert s.is_demo and s.database_url == "sqlite:////tmp/opspilot.db"


def test_demo_mode_creates_demo_users_production_does_not(db, monkeypatch):
    from app.core import config
    for u in db.query(User).all():
        db.delete(u)
    db.commit()
    monkeypatch.setattr(config, "get_settings", lambda: Settings(environment="demo", secret_key="y" * 40, database_url="sqlite://"))
    monkeypatch.setattr(seed, "get_settings", config.get_settings)
    seed.ensure_users(db)
    assert {u.email for u in db.query(User).all()} >= {"admin@opspilot.local", "viewer@opspilot.local"}


def test_health_reports_environment_for_the_login_hint(client):
    assert client.get("/api/v1/health").json()["environment"] == "test"


def test_wildcard_cors_is_ignored():
    assert Settings(cors_origins="*,https://app.example.com").cors_origin_list == ["https://app.example.com"]


def test_no_demo_users_in_production(db, monkeypatch):
    from app.core import config
    for u in db.query(User).all():
        db.delete(u)
    db.commit()
    monkeypatch.setattr(config, "get_settings", lambda: Settings(**GOOD, admin_email="boss@example.com", admin_password="a-strong-password-1"))
    monkeypatch.setattr(seed, "get_settings", config.get_settings)
    seed.ensure_users(db)
    emails = [u.email for u in db.query(User).all()]
    assert emails == ["boss@example.com"]  # no *@opspilot.local accounts, no default password


def test_api_security_headers_and_no_store(client, auth):
    r = client.get("/api/v1/orders", headers=auth)
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_cors_rejects_unknown_origin(client):
    r = client.options("/api/v1/orders", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
