# Database

PostgreSQL in Docker/production (SQLite for zero-dependency local runs and the test-suite). Schema managed by **Alembic** (`backend/migrations`, initial revision `0001`); SQLAlchemy 2 models in `backend/app/models`. UUID primary keys (portable `Uuid` type), timezone-aware UTC timestamps (a `UTCDateTime` type guarantees tz-awareness on every backend), enums stored as constrained strings (`native_enum=False` + CHECK).

```
users
restaurants ──< orders >── customers
                │  └──< order_items
                │  └──< order_events
couriers ───────┘ (orders.courier_id, nullable)
incidents >── orders (nullable)  >── restaurants (nullable)
operational_events (activity feed + incident change history, entity_type/entity_id)
agent_conversations ──< agent_messages
agent_conversations ──< agent_tool_executions
simulation_state (single row: clock offset)
```

| Table | Highlights |
|---|---|
| `users` | unique email, bcrypt hash, role `ADMIN|OPERATOR|VIEWER` |
| `restaurants` | `code` unique, status, baseline `avg_prep_minutes`, `delay_factor` (simulation lever), `rating` |
| `customers` | fictitious name/phone/address |
| `orders` | `code` unique; `status`; `est_prep_minutes`, `est_delivery_minutes`, `promised_at`, `ready_at`, `picked_up_at`, `delivered_at`, `cancelled_at`; `sim_*_minutes`; indexes `(status, created_at)`, `(restaurant_id, created_at)`, `courier_id`, `created_at` |
| `order_items` / `order_events` | cascade with the order; events carry `from_status`, `to_status`, `actor` |
| `couriers` | `code`, status, simulated `lat/lng`, `total_deliveries`, `avg_delivery_minutes`, `updated_at` |
| `incidents` | `code` (`OP-001`), type, priority, status, assignee, resolution, timestamps; index `(status, priority)` |
| `operational_events` | severity, message, JSON payload (incident changes store `{from,to}` per field) |
| `agent_*` | conversations, messages (`metadata` JSON: tool runs, recommendations, mode) and an audit row per tool execution (`SUCCESS | ERROR | PENDING_CONFIRMATION | CONFIRMED | REJECTED`) |

Delay/risk are **derived**, never stored (see ARCHITECTURE.md).

## Migrations
```bash
cd backend
alembic upgrade head          # DATABASE_URL from the environment
alembic revision --autogenerate -m "describe change"
```
The initial migration was generated from the models and verified with `upgrade head` / `downgrade base` on SQLite; CI additionally applies it to a real PostgreSQL 16 service container and runs a smoke test. (Not executed on PostgreSQL in the authoring environment, which had no Docker/PostgreSQL.)

## Demo data
`app/services/seed.py` (deterministic, seed 42): 16 restaurants (two deliberately slow kitchens, one paused), 34 couriers (5 offline), ~108 orders spread over ~72 h plus every live situation (healthy, delayed with assorted severities, at risk, waiting without courier, cancelled, delivered), 24 incidents in all statuses, event history and activity feed. All names/addresses/phones are fictitious. Restore with `POST /simulation/reset`, the *Restaurar demonstração* button, or `python -m app.cli reset`.
