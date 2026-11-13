# Architecture

OpsPilot AI is a modular monolith: one FastAPI service, one React SPA, one relational database. No message queue, no background workers: the simulator advances only when the user asks it to.

```
┌────────────┐  HTTPS/JSON (JWT)   ┌──────────────────────────────────────────────┐   SQL    ┌────────────┐
│ React SPA  │ ──────────────────► │ FastAPI                                       │ ───────► │ PostgreSQL │
│ (Vite, TS) │ ◄────────────────── │  api/  → services/ → rules/ (pure functions)  │ ◄─────── │ (SQLite in │
└────────────┘                     │        └ agents/ → tools/ → services/         │          │ dev/tests) │
                                   │                 └ providers (Anthropic | demo)│          └────────────┘
                                   └──────────────────────────────────────────────┘
```

## Backend layers (`backend/app`)

| Package | Responsibility |
|---|---|
| `api/` | HTTP only: routing, auth dependencies, request/response shapes. No business logic. |
| `schemas/` | Pydantic request bodies (validation). |
| `services/` | Use cases and queries: orders (state machine), couriers (recommendation), restaurants, incidents, metrics, alerts, reports, simulation, seed. Services serialise to dicts that are reused by the API **and** by the agent tools, so both always agree. |
| `rules/` | **Business rules as pure functions** (`engine.py`): delay, risk, priority, restaurant alert, capacity alert, stale critical incident, status transitions. All thresholds live in `RuleConfig` (overridable by `RULES_OVERRIDES`). No DB, HTTP or prompts here. |
| `models/` | SQLAlchemy 2 entities. `repositories/` is reserved: queries currently live in the services, which is enough at this size. |
| `tools/` | The agent's 12 tools: Pydantic arguments, permission flag, handler → service. |
| `agents/` | Copilot loop, provider abstraction (`AnthropicProvider`, `DemoProvider`), safety helpers. |
| `prompts/` | System prompt text (instructions only, no rules). |
| `core/` | Settings, DB, JWT/bcrypt, error envelope. |

### Request flow (e.g. `GET /orders?situation=delayed`)
`api/operations.py` → `services.clock.now()` (simulated clock) → `services.orders.query_orders` → for each order `rules.engine.assess_order(snapshot, now, cfg)` → JSON.
Delay/risk is never stored: it is derived from timestamps and the rules every time, so changing a rule or advancing the clock is reflected instantly everywhere.

### Simulated clock
`now = real UTC + simulation_state.offset_minutes`. `POST /simulation/advance` moves the offset and progresses orders (confirm → prepare → ready → pickup → deliver) with timestamps derived from each order's `sim_prep_minutes` / `sim_travel_minutes`. Because the simulator writes to the real tables, the dashboard, reports and the agent tools reflect it.

### Order state machine
`RECEIVED → CONFIRMED → PREPARING → READY_FOR_PICKUP → (WAITING_COURIER) → IN_DELIVERY → DELIVERED`, with `CANCELLED` reachable from any non-terminal state. Defined once in `rules/engine.py::ALLOWED_TRANSITIONS`, enforced in `services.orders.change_status` (HTTP 422 `invalid_transition`). `IN_DELIVERY` requires a courier. Courier statuses are kept consistent automatically (assigned → delivering → available).

### Courier assignment
Never implicit. `recommend` ranks candidates; assignment is `POST /orders/{id}/assign` (human) or, inside the simulator only, the explicit `auto_assign` rule that takes the top recommendation.

**Recommendation score (0–100)** – `services/couriers.py::recommend`, only `AVAILABLE` couriers are eligible:

| Criterion | Points |
|---|---|
| Distance courier → restaurant (haversine, linear, 0 at `max_courier_distance_km` = 8) | up to 50 |
| Workload: 0 / 1 / 2+ active orders | 25 / 10 / 0 |
| Idle time (1 pt per minute, capped) | up to 15 |
| Fairness: fewer lifetime deliveries score higher | up to 10 |

Couriers farther than `max_courier_distance_km` are excluded (reported as `excluded_too_far`). Each candidate returns the score breakdown and human-readable reasons.
*Limitations:* straight-line distance (no routing/traffic), the distance to the customer is not considered, weights are heuristic and not learned, only AVAILABLE couriers are candidates (no batching of multiple orders), ETA uses a constant 22 km/h.

## Frontend (`frontend/src`)
React 19 + TypeScript + Vite + Tailwind v4, shadcn-style components (Radix primitives + `class-variance-authority`), TanStack Query for server state, React Router, React Hook Form + Zod for forms, Recharts for charts. Pages are lazy-loaded. `lib/api.ts` is the only place that talks HTTP (adds the JWT, normalises the error envelope, signals 401). The UI holds **no** business rules: delay/risk/alerts all come from the backend.

## AI integration
See [AI_AGENT.md](AI_AGENT.md).

## Data flow summary
1. User logs in → JWT (HS256, expiring) stored in `localStorage`.
2. Pages fetch via TanStack Query; mutations invalidate every query (data is interlinked).
3. Copilot: `POST /ai/chat` → loop → tools → services → DB → answer + tool audit + recommendations.
4. Actions that change data from chat require `POST /ai/executions/{id}/confirm`.

## Configuration
Everything via environment variables (`.env.example`). Production refuses to start with a weak `SECRET_KEY` or SQLite.
