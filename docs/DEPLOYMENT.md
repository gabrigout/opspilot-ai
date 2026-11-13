# Deployment

> **Status:** configuration is provided. A free single-project Vercel setup (section 0) was added, but **it had not been deployed when this was written**. The older standalone frontend import on Vercel has no API, so its login cannot work.
>
> **Open it without installing anything:** the repository includes a `.devcontainer` that runs the Docker Compose stack in **GitHub Codespaces** (see the README button).

Target topology: **frontend on Vercel**, **backend as a Docker web service** (Render blueprint included), **managed PostgreSQL**.

## 0. Free public demo: frontend + backend in ONE Vercel project (no credit card)
The root [`vercel.json`](../vercel.json) uses **Vercel Services** (beta): `frontend/` is served at `/` and the FastAPI app in `backend/` at `/api/*` (the service receives the original path, so `/api/v1/...` works unchanged). Same origin, so no CORS setup.

1. Vercel → **Add New → Project** → import `gabrigout/opspilot-ai` (repository root; it will detect the two services — accept the multi-service setup).
2. Add one environment variable: **`SECRET_KEY`** = a random string of 32+ characters (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`).
3. Deploy. On Vercel the backend defaults to **demo mode** (`ENVIRONMENT=demo`, SQLite in `/tmp`) and **refuses to start without a strong `SECRET_KEY`**.

What demo mode means (read this before sharing the link):
- Demo users exist with the documented password (`admin@opspilot.local` / `opspilot-demo`), shown on the login page. Anyone with the link can log in as admin; the data is fictitious, resettable (*Restaurar demonstração*) and the AI runs in demo mode (do **not** set `ANTHROPIC_API_KEY` on a public demo).
- The database is **SQLite in `/tmp`: ephemeral and per function instance**. Data resets on cold starts and can differ between instances. It is a demo, not a persistent deployment. For persistence use the Postgres route below.
- The first request after idle is slow (cold start + seeding the demo dataset).
- Vercel Services is in beta, and this configuration was written from the Vercel docs and has not been executed on Vercel by the authors until you deploy it.

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
