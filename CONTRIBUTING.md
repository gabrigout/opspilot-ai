# Contributing to OpsPilot AI

Thanks for your interest! OpsPilot AI is an independent demonstration project; contributions that improve code quality, tests, docs and the agent's safety are welcome.

## Setup

```bash
# backend (Python 3.12)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q && ruff check app tests

# frontend (Node 22)
cd frontend
npm ci
npm run typecheck && npm test
```

## Guidelines

- **Keep layers separate.** Business rules live in `backend/app/rules`, data access/queries in `services`, HTTP in `api`, agent logic in `agents`/`tools`. No business conditions in React components or prompts.
- **New agent tool?** Add a Pydantic args model + handler in `app/tools/definitions.py`, register it, add tests in `tests/test_agent.py`, and document it in `docs/AI_AGENT.md`. Tools that change data must set `mutates=True` (they require human confirmation).
- **Tests are required** for rules, services and tools. Never mark work done without running the suites.
- **No real data.** Everything must stay fictitious. Never commit secrets, `.env` files or tokens.
- **No brand assets.** Do not add logos, names or identity of real delivery companies.
- Commits: small and focused, imperative mood (`feat: add courier fairness score`). Use conventional prefixes (`feat`, `fix`, `docs`, `test`, `chore`).

## Pull requests

1. Fork and branch from `main`.
2. Run backend and frontend checks locally (see above); CI runs the same plus PostgreSQL migrations.
3. Describe what changed, why, and how you verified it.
