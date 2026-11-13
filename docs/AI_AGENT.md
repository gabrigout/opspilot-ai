# AI Agent – OpsPilot AI Copilot

The Copilot is a **tool-using agent**, not a chatbot: it answers from data returned by controlled backend tools and clearly separates *consulted data* from *AI recommendations*.

## Architecture

```
POST /api/v1/ai/chat
   │ rate limit → length/shape validation → unsafe-request screen
   ▼
Copilot loop (agents/copilot.py)  ── max_iterations / timeout / tool-call budget
   │   provider.complete(system, messages, tool_schemas)
   │        ├─ AnthropicProvider  (official SDK, Messages API tool use)
   │        └─ DemoProvider       (no LLM: intent patterns → tool calls → renders from results)
   │   tool_use ─► tools.execute_tool(name, args)  ── validate (Pydantic) → permission → handler → service → DB
   │   tool_result (wrapped as quoted data) ─► back to the provider
   ▼
final text  ─► split "### Recomendações" ─► persist message + tool executions ─► JSON
```

Both providers implement the same `LLMProvider.complete()` interface and use Anthropic-style content blocks (`text`, `tool_use`, `tool_result`), so the loop, tools, persistence and safety layers are identical in demo and real mode.

## Tool-calling cycle (explicit)
1. Receive the message; rate-limit; reject unsafe requests (see Security).
2. Build `messages` = last 10 messages of the conversation + the new one.
3. Call the provider with the system prompt and the 12 tool JSON schemas (generated from the Pydantic argument models).
4. If the provider returns `tool_use` blocks: for each call → `execute_tool` validates arguments, checks the role, runs the handler, and records an `agent_tool_executions` row (arguments, result, status, duration).
5. Results are appended as `tool_result` blocks wrapped in `<tool_data tool="…">{json}</tool_data>` and sent back.
6. Repeat until the provider returns text, or a limit is hit: `AGENT_MAX_ITERATIONS` (default 6), `AGENT_TIMEOUT_SECONDS` (default 60), 8 tool calls per turn. Hitting a limit returns a safe message, never loops.
7. The final text is split at `### Recomendações`: everything before is shown as **Dados consultados**, the list after as **Recomendações geradas pela IA**. Order codes mentioned are extracted as clickable references.
8. The assistant message (with `tool_runs`, `recommendations`, `order_refs`, `mode`, `model`) is stored in `agent_messages`.

## Tools
| Tool | Purpose | Notes |
|---|---|---|
| `get_order` | One order: status, restaurant, courier, deadlines, situation | by UUID or code (`ORD-1042`, `#1042`, `1042`) |
| `search_orders` | Filter by status, situation, restaurant, period | `limit` ≤ 50, summary by status |
| `get_delayed_orders` | Orders past their promised time | delay minutes + priority from rules |
| `get_at_risk_orders` | Orders with risk of delay | each with the rule(s) that fired |
| `get_available_couriers` | Available couriers, location, load | |
| `recommend_courier` | Ranked candidates for an order | **never assigns**; returns score breakdown |
| `get_restaurant_performance` | Orders, prep time, cancellations, delays vs operation average | |
| `get_operational_metrics` | KPIs for any period (1–720 h) | |
| `create_incident` | Creates an incident | **mutating → confirmation required** |
| `generate_operational_report` | general / delays / restaurants / couriers / incidents | built from the same queries as the Reports page |
| `get_open_incidents` | Open incidents by priority | |
| `get_order_history` | Event history of an order | |

## Human-in-the-loop for changes
`create_incident` is declared `mutates=True`. When the model (or demo provider) calls it, `execute_tool` **does not run the handler**: it stores an `agent_tool_executions` row with status `PENDING_CONFIRMATION` and returns the proposal. The UI shows a confirmation card; only `POST /ai/executions/{id}/confirm` (authenticated, owner or admin, role must be able to write, single use) executes it with `confirmed=True`. The LLM cannot set that flag.

## Security
- **No arbitrary access**: the model can only request the 12 registered tools; no SQL, shell, file or environment access exists in the tool set.
- **Argument validation** by Pydantic (types, enums, ranges, max lengths); invalid calls come back as `Invalid arguments: …` so the model can retry.
- **Permissions**: viewers cannot run mutating tools, even if confirmed.
- **Prompt injection**: (1) user messages matching jailbreak / secret-exfiltration / SQL / code-execution patterns are refused before any provider call; (2) tool results are JSON-quoted inside `<tool_data>` with control characters stripped, strings truncated to 400 chars, and the delimiter neutralised, and the system prompt states that tool data is never instructions; (3) the model has no tool that could act on injected text anyway except the confirmation-gated `create_incident`.
- **Rate limiting** per user (`AGENT_RATE_LIMIT_PER_MINUTE`), in memory.
- **Audit**: every tool execution is persisted with arguments, result/error and duration.
- **Sensitive data**: API keys live only in backend env vars and are never returned by any endpoint; all business data is fictitious.
- The screen for unsafe requests is a conservative pattern list, not a guarantee. See [SECURITY.md](SECURITY.md).

## Demo mode (no external LLM)
Active when there is no `ANTHROPIC_API_KEY` or `AI_PROVIDER=demo`. The UI and every response show **"Modo demonstrativo · sem LLM externo"**. The `DemoProvider`:
- maps the question to tool calls with accent-insensitive keyword/regex rules (delays, risk, overview, restaurants, couriers, incidents, reports, an order code, history, recommendation, "abra uma ocorrência …: descrição");
- executes the **real** tools and renders the answer only from their results (templates, not generation);
- answers unknown questions with an honest help message listing what it can do.
It does not generate free text, reason across tools, or understand paraphrases outside its patterns. That is a deliberate, visible limitation.

## Configuring a real provider
```env
AI_PROVIDER=auto              # or anthropic
ANTHROPIC_API_KEY=sk-ant-...  # backend env only
ANTHROPIC_MODEL=claude-sonnet-5-5
```
Restart the backend. `GET /api/v1/ai/status` and the header indicator show `anthropic · <model>`. Provider failures (auth, network, rate limit, 5xx) are caught: the user gets a clear message and **no data is changed**. If `AI_PROVIDER=anthropic` but no key is set, the app falls back to demo mode and reports a `configuration_warning`.

> The real-provider path is covered by unit tests with a scripted fake provider (tool loop, limits, failure handling, injection delimiting). It has **not** been exercised against the live Anthropic API in this repository's test suite because no API key is available in CI.

## Limitations
- Conversation memory is the last 10 messages; no long-term memory or retrieval.
- The tool set is read-mostly; the only write is incident creation.
- Rate limiter and token revocation are per-process.
- Output language is pt-BR (system prompt).
