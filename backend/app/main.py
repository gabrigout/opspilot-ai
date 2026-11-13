"""OpsPilot AI – FastAPI application factory."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (register tables)
from app.api import ai, auth, insights, operations
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine, get_db
from app.core.errors import register_error_handlers
from app.models import Restaurant
from app.services import seed

log = logging.getLogger("opspilot")
API = "/api/v1"


def bootstrap() -> None:
    """Create tables when no migration ran (dev/SQLite) and seed demo data once."""
    s = get_settings()
    if s.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.ensure_users(db)
        if s.seed_demo_data and not db.scalars(select(Restaurant).limit(1)).first():
            log.info("Seeding demo data: %s", seed.seed_demo(db))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="OpsPilot AI API",
        version="1.0.0",
        description="Plataforma de operações de delivery com agente de IA (tool calling). "
                    "Projeto independente de demonstração: todos os dados são simulados.",
        lifespan=lifespan,
        docs_url=f"{API}/docs", redoc_url=None, openapi_url=f"{API}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)

    @app.get(f"{API}/health", tags=["system"], summary="Health check (sem autenticação)")
    def health(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {"status": "ok", "environment": s.environment, "version": app.version}

    for r in (auth.router, operations.router, insights.router, ai.router):
        app.include_router(r, prefix=API)
    return app


app = create_app()
