# REST API

Base path `/api/v1`. Interactive docs (Swagger UI): `http://localhost:8000/api/v1/docs` · OpenAPI JSON: `/api/v1/openapi.json`.

## Conventions
- **Auth**: `Authorization: Bearer <JWT>` (from `POST /auth/login`, expires after `ACCESS_TOKEN_EXPIRE_MINUTES`). Only `/health` and `/auth/login` are public.
- **Roles**: `ADMIN`, `OPERATOR` (can change data), `VIEWER` (read-only; `403` on writes). `simulation/reset` is admin only.
- **Errors** always use one envelope, with no stack traces or internals:
  ```json
  {"error": {"code": "invalid_transition", "message": "Cannot move order ORD-1 from RECEIVED to DELIVERED. Allowed: CONFIRMED, CANCELLED", "details": {…}}}
  ```
  Codes: `validation_error` (422, `details` = list of `{field,message}`), `unauthorized` (401), `forbidden` (403), `not_found` (404), `conflict` (409), `invalid_transition` (422), `rate_limited` (429), `internal_error` (500).
- **Lists** of orders / activity are paginated: `{items, total, page, page_size}`. Other lists return `{items, total}`.
- **Orders** can be addressed by UUID or code (`ORD-1042`, `1042`, `#1042`). Incidents by UUID or code (`OP-001`). Couriers by UUID or `E-001`. Restaurants by UUID, code (`R-001`) or name.
- `hours` / `period_hours`: 1–720.
- All data is simulated; responses that aggregate data include `simulated_data: true` where relevant.

## System & auth
| Method & path | Description |
|---|---|
| `GET /health` | DB-checked health check (no auth) |
| `POST /auth/login` `{email,password}` | → `{access_token, token_type, expires_in, user}` |
| `POST /auth/logout` | Revokes the current token (in-memory denylist) |
| `GET /auth/me` | Current user |

## Dashboard
| Path | Description |
|---|---|
| `GET /dashboard/overview?hours=24` | `{kpis, charts, alerts, activity}` in one call |
| `GET /dashboard/metrics?hours=` | KPIs: `total_orders, in_progress, delivered, delayed, at_risk, cancelled, waiting_courier, avg_delivery_minutes, available_couriers, total_couriers, open_incidents` |
| `GET /dashboard/charts?hours=` | Series: `order_volume, orders_by_status, avg_delivery_time, incident_distribution, restaurant_performance, cancellations` (hourly buckets up to 72 h, daily above) |
| `GET /dashboard/alerts` | Rule-based alerts `{id, rule, level: INFO|WARNING|CRITICAL, title, message, orders[]}` |
| `GET /activity?severity=&entity_type=&page=&page_size=` | Operational event history |

## Orders
| Path | Description |
|---|---|
| `GET /orders` | Filters: `status`, `restaurant`, `q` (code), `situation` (`delayed|at_risk|on_track`), `period_hours`, `since`, `until`, `no_courier`, `page`, `page_size` (≤100) |
| `GET /orders/{id}` | Detail: items, customer (fictitious), history, `allowed_transitions`, assessment (`is_delayed`, `delay_minutes`, `delay_priority`, `at_risk`, `risk_reasons`, `remaining_minutes`) |
| `GET /orders/{id}/history` | Event list |
| `PATCH /orders/{id}/status` `{status, reason?}` | Validated transition (`422 invalid_transition`) |
| `GET /orders/{id}/courier-recommendations?limit=` | Ranked couriers with score breakdown. **Does not assign.** |
| `POST /orders/{id}/assign` `{courier_id}` | Human-approved assignment (`409` if courier not AVAILABLE or order past pickup) |

## Couriers & restaurants
| Path | Description |
|---|---|
| `GET /couriers?status=` | List + `summary` by status |
| `GET /couriers/available` | Available couriers; `shortage: true` when none |
| `GET /couriers/{id}` | Detail + `recent_orders` |
| `PATCH /couriers/{id}/status` `{status}` | `409` if inconsistent with active orders |
| `GET /restaurants?status=&period_hours=` | Performance rows + `operation_avg_prep_minutes` |
| `GET /restaurants/{id}` | Row + `recent_orders` |

## Incidents
| Path | Description |
|---|---|
| `GET /incidents?status=&priority=&open_only=&order=` | Sorted by priority |
| `POST /incidents` `{type, priority, description, order_ref?, title?, assignee?}` | `201` |
| `GET /incidents/{id}` | Detail + `history` (every change with from/to) |
| `PATCH /incidents/{id}` `{status?, priority?, assignee?, resolution?, description?}` | Resolve/close require a resolution; `CLOSED` only from `RESOLVED` and is final |

## Reports
`GET /reports` (kinds) · `GET /reports/{kind}?hours=` (kind ∈ `general|delays|restaurants|couriers|incidents`; `operational` = `general`) → `{title, period, indicators, summary, problems, recommendations, table}` · `GET /reports/{kind}/export?format=csv|pdf&hours=` (file download).

## Simulation
| Path | Description |
|---|---|
| `GET /simulation/status` | Simulated clock and counters |
| `POST /simulation/advance` `{minutes (0–240], auto_assign}` | Progresses orders; returns `{status_changes, assignments, newly_delayed}` |
| `POST /simulation/actions` `{action, count?, restaurant?, factor?}` | `spawn_orders, demand_spike, reduce_couriers, restore_couriers, restaurant_delay, cancel_orders, generate_incidents` |
| `POST /simulation/reset` | Admin. Rebuilds the demo dataset |

## AI
| Path | Description |
|---|---|
| `GET /ai/status` | `{mode: demo|llm, provider, model, label, configuration_warning, tools[], limits}` |
| `POST /ai/chat` `{message (1–2000), conversation_id?}` | → `{conversation_id, message:{content, metadata:{mode, tool_runs[], recommendations[], order_refs[], …}}}` |
| `GET /ai/conversations` · `GET /ai/conversations/{id}` | Own conversations |
| `POST /ai/executions/{id}/confirm` `{approve}` | Approve/reject a pending tool action (single use) |

## Settings
`GET /settings/rules` (active thresholds) · `GET /settings/system`.
