"""Application settings, loaded from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRETS = {
    "", "change-me", "changeme", "secret", "dev-secret-change-me",
    "dev-secret-change-me-dev-secret-change-me",  # the development defaults (config, compose, .env.example)
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # development | test | production
    database_url: str = "sqlite:///./opspilot.db"
    secret_key: str = "dev-secret-change-me-dev-secret-change-me"  # >= 32 bytes for HS256; rejected in production
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Demo data / users
    seed_demo_data: bool = True
    admin_email: str | None = None  # used to bootstrap an admin in production
    admin_password: str | None = None

    # AI
    ai_provider: str = "auto"  # auto | anthropic | demo
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    agent_max_iterations: int = Field(6, ge=1, le=12)
    agent_timeout_seconds: int = Field(60, ge=5, le=300)
    agent_rate_limit_per_minute: int = Field(20, ge=1)

    # Operational rules overrides, e.g. RULES_OVERRIDES='{"risk_remaining_minutes": 12}'
    rules_overrides: dict[str, float] = Field(default_factory=dict)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip() and o.strip() != "*"]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if self.is_production:
            if self.secret_key in INSECURE_SECRETS or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be a random string with >= 32 chars in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Use a managed PostgreSQL DATABASE_URL in production")
            if self.admin_password is not None and len(self.admin_password) < 12:
                raise ValueError("ADMIN_PASSWORD must have at least 12 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
