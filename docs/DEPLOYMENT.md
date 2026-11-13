# Deployment

> **Status:** configuration is provided but **nothing has been deployed** by the project authors. No public URL exists yet.

Target topology: **frontend on Vercel**, **backend as a Docker web service** (Render blueprint included), **managed PostgreSQL**.

## 1. Backend + database (Render example)
1. Push the repository to GitHub.
2. In Render: *New → Blueprint* and select the repo (`render.yaml` creates the web service from `backend/Dockerfile` and a PostgreSQL database; `DATABASE_URL` is injected, `SECRET_KEY` is generated).
3. In the service's environment set:
   - `CORS_ORIGINS` = your Vercel URL (e.g. `https://opspilot-ai.vercel.app`, no wildcard)
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD` = the first admin (no demo users exist in production)
   - `ANTHROPIC_API_KEY` (optional; without it the Copilot runs in demo mode)
   - `SEED_DEMO_DATA=true` to load fictitious data into the empty database (set `false` for an empty system)
4. The container runs `alembic upgrade head` and then Uvicorn. Health check: `GET /api/v1/health`.

Any Docker-capable platform (Fly.io, Railway, Cloud Run, a VM with `docker-compose.prod.yml`) works the same way; the app reads `PORT`, `DATABASE_URL` (`postgres://`, `postgresql://` and `postgresql+psycopg://` accepted) and the variables in `.env.example`.

## 2. Frontend (Vercel)
- Import the repo, **Root Directory** `frontend`, framework Vite (`vercel.json` provides SPA rewrites and security headers).
- Environment variable `VITE_API_URL` = backend base URL (e.g. `https://opspilot-api.onrender.com`).
- Deploy, then add the resulting URL to the backend's `CORS_ORIGINS` and redeploy the backend.

## 3. Single host with Docker
```bash
cp .env.example .env.production       # fill in real secrets
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```
Put a TLS-terminating reverse proxy in front (Caddy, Traefik, cloud LB).

## Local Docker notes
- `docker compose up -d --build` starts `db` → `backend` (waits for a healthy DB, runs migrations, seeds) → `frontend` (waits for a healthy backend). Open <http://localhost:8080>.
- nginx resolves `backend` per request through Docker's DNS (`resolver 127.0.0.11`), so it starts and recovers even if the API container is recreated.
- Low-RAM hosts (~4 GB): create `%USERPROFILE%\.wslconfig` with `[wsl2]` `memory=2GB` `swap=2GB` `processors=2`, run `wsl --shutdown`, reopen Docker Desktop and allow 1–2 minutes for the engine. The first build can take several minutes.
- Stop with `docker compose down` (data kept in the `pgdata` volume; add `-v` to delete it).

## Production checklist
- [ ] `SECRET_KEY` random ≥ 32 chars (the app refuses to start otherwise)
- [ ] Managed PostgreSQL with backups; `DATABASE_URL` set
- [ ] `CORS_ORIGINS` limited to the real frontend origin(s)
- [ ] Admin credentials set; no default passwords
- [ ] HTTPS everywhere
- [ ] Remember rate limiting / token revocation are per-process (see SECURITY.md)
