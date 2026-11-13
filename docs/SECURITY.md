# Security

OpsPilot AI is a demonstration project with simulated data, but it applies real application-security practices.

## Implemented
| Area | Measure |
|---|---|
| Authentication | `POST /auth/login`; bcrypt password hashes; JWT HS256 with `exp`, `iat`, `jti`; generic "Invalid email or password" for unknown user/wrong password (+ dummy hash to even out timing); per-email login rate limit (10/min); `POST /auth/logout` revokes the token |
| Authorization | Every route except `/health` and `/auth/login` requires a valid token; roles `ADMIN/OPERATOR/VIEWER`; writes need ADMIN/OPERATOR; reset is ADMIN only; AI conversations are private to their owner |
| Demo user | Created **only when `ENVIRONMENT != production`** (`admin@opspilot.local`, `operador@…`, `viewer@…`, password `opspilot-demo`, local use only). In production no demo users exist; an admin is bootstrapped from `ADMIN_EMAIL`/`ADMIN_PASSWORD` or `python -m app.cli create-admin` |
| Secrets | Only via environment; `.env*` is git-ignored; production **refuses to start** with a weak/default `SECRET_KEY` (<32 chars) or SQLite. The frontend never receives any key |
| Input validation | Pydantic on every body/query (enums, ranges, max lengths); consistent error envelope; 500s return a generic message and log details server-side only |
| CORS | Explicit allow-list from `CORS_ORIGINS`; wildcard `*` is ignored; credentials disabled; methods and headers restricted |
| SQL | SQLAlchemy parameterised queries only; the agent has no SQL tool |
| XSS | React escaping; the agent's Markdown is rendered by a small renderer that never uses `dangerouslySetInnerHTML` (unit-tested) |
| Agent | See [AI_AGENT.md](AI_AGENT.md): allow-listed tools, argument validation, role checks, confirmation for writes, injection delimiting, request screening, rate limit, audit log |
| Containers | Backend runs as non-root; nginx adds `nosniff`, `X-Frame-Options`, `Referrer-Policy` |
| CI | Lint, tests, migrations on PostgreSQL, build |

## Known limitations
- JWT is stored in `localStorage` (simple for a SPA, exposed to XSS if one is ever introduced). A production hardening would use `HttpOnly` cookies + CSRF protection.
- Token revocation and rate limiters are **in-memory** (per process, reset on restart; not shared across replicas). Use Redis/DB for multi-instance deployments.
- No refresh tokens, password reset, MFA or account lockout beyond the login rate limit.
- The unsafe-request screen is a pattern list: it reduces obvious abuse but cannot stop all prompt-injection. The real controls are structural (limited tool set, confirmation, quoting).
- No TLS termination here: put it behind HTTPS (Vercel/Render provide it).
- No dependency/secret scanning is configured yet (see ROADMAP).
- The authoring environment had no Docker, so container builds and the PostgreSQL path were validated only by CI configuration, not executed locally.

## Reporting a vulnerability
Open a private security advisory on the repository, or contact the maintainers. Do not include real credentials in issues.
