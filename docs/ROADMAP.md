# Roadmap

**Done (v1.0):** orders with validated state machine; couriers with explainable recommendation; restaurants analytics; incidents with full history; rule-based alerts; dashboard with 6 charts; 5 report types with CSV/PDF export; user-controlled simulator; Copilot with 12 tools, demo + Anthropic providers, confirmation flow; JWT auth with roles; Alembic migrations; Docker Compose; CI.

## Next
1. **Browser E2E tests** (Playwright) for login → dashboard → order → assign → copilot flows, plus screenshots for the README.
2. **Live-provider integration test** (opt-in, behind an API-key secret) and streaming responses in the Copilot UI.
3. **Auth hardening:** HttpOnly cookie sessions + CSRF, refresh tokens, Redis-backed revocation/rate limiting, user administration screen.
4. **Dependency & secret scanning** (Dependabot, CodeQL, gitleaks) in CI.
5. **Real map view** for couriers/restaurants (the coordinates already exist) and ETA by route instead of straight-line distance.
6. **Rules editor** in the UI (persisted `RuleConfig` per tenant) with audit trail.
7. **Agent:** more tools (reassign courier proposals, customer-message drafts), retrieval over incident history, evaluation suite with golden questions.
8. **Multi-tenant** model and external ingestion API/webhooks for real order feeds.
9. **Observability:** structured logs, OpenTelemetry traces for tool execution, metrics endpoint.
