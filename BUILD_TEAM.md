# World Oracle — BUILD TEAM
## Platform & Infrastructure Directives

---

## Your Role

You are the Build Team. You own the platform — the body of the oracle.
You make it run, scale, serve, persist, and monitor.

You do NOT touch modules/. That is Oracle Team territory.
You do NOT change core/registry.py without explicit agreement from both teams.

---

## What You Own

```
core/          ← the spine (already built — maintain and extend)
output/        ← Layer 4 formatter (already built)
main.py        ← entry point (already built)
api/           ← FastAPI REST server (BUILD THIS NEXT)
dashboard/     ← Streamlit live dashboard (Phase 3)
tests/         ← full test suite
requirements.txt
.env.example
Dockerfile
```

---

## Phase 2 — Your Immediate Tasks

### Task B-1: FastAPI Server

Build `api/server.py` — a FastAPI app that exposes the oracle over HTTP.

```
POST /api/query
  body: { "query": "Will crude oil rise over the next 6 weeks?" }
  returns: OracleResponse (see output/formatter.py)

GET  /api/health
  returns: module registry status + feed health

GET  /api/modules
  returns: registered modules, their temporal coverage, confidence ranges

GET  /api/history
  returns: last N oracle calls with outcomes (for track record)
```

Key requirements:
- Async throughout (the oracle is async)
- Return 200 with status=INSUFFICIENT_SIGNAL for abstain cases (not 4xx)
- Log every query + response to the signal store
- Rate limit: 60 requests/minute default

### Task B-2: Signal Store

Build `db/signal_store.py` — persistence layer for oracle calls.

```python
# What to store per oracle call:
{
  "query":        str,
  "domain":       str,
  "timestamp":    ISO,
  "response":     full OracleResponse dict,
  "outcome":      None  # filled in later when market verdict is known
}
```

Use SQLite for now (easy local dev). Swap to PostgreSQL for production.
This store is the track record that makes Tier 2 monetisation possible.

### Task B-3: Feed Health Monitor

Build `core/feed_monitor.py` — runs health checks across all registered modules.

```python
async def check_all_feeds(registry: ModuleRegistry) -> dict:
    # Calls module.health_check() for each registered module
    # Returns {module_id: {feed_id: {status, last_updated, staleness}}}
```

Trigger on startup and every 15 minutes. Log stale feeds as warnings.

---

## Phase 3 — Dashboard

Build `dashboard/app.py` using Streamlit.

Pages:
1. **Live Oracle** — run a query, see the full response with reasoning trace
2. **Signal History** — past oracle calls, confidence scores, outcomes
3. **Feed Health** — which data feeds are live, which are stale
4. **Breathing Map** — visual of T3→T0 layers with current signal state

Design principles:
- Show confidence bands, not false precision
- Make the ABSTAIN state obvious and prominent (it's a feature, not a failure)
- The reasoning trace (T3→T0) should be readable by a non-technical trader

---

## Code Standards

```python
# Always async for I/O
async def my_function() -> ReturnType:

# Type hints everywhere
def process(signal: Signal, threshold: float) -> ConfidenceResult:

# Explicit error handling — never silent failures
try:
    result = await feed.get()
except FeedError as e:
    logger.warning(f"Feed unavailable: {e}")
    # return degraded result, not crash

# No magic numbers — name your constants
CONFIDENCE_THRESHOLD_DEFAULT = 0.65
RATE_LIMIT_PER_MINUTE = 60
```

---

## Testing Rules

- Write tests BEFORE implementing (TDD where possible)
- All tests in tests/ directory
- Run `python -m pytest tests/ -v` before every commit
- 19 foundation tests must always pass
- New feature = new test file

---

## Git Workflow

```bash
# Your branches live under build/
git checkout -b build/fastapi-server
git checkout -b build/signal-store
git checkout -b build/dashboard

# PR into dev, never directly into main
# main is always deployable
```

---

## Environment Variables

```bash
# .env (never commit this)
ANTHROPIC_API_KEY=sk-ant-...
EIA_API_KEY=...           # free at eia.gov
DATABASE_URL=sqlite:///world_oracle.db
REDIS_URL=redis://localhost:6379
PORT=8000
```

---

## Current Foundation (already built — do not rewrite)

```
core/registry.py          ← OracleModule contract + ModuleRegistry
core/query_engine.py      ← Layer 1 — LLM decomposition + DAG builder
core/temporal_engine.py   ← T0–T3 signal lifecycle + decay
core/confidence_engine.py ← weighted scoring + abstain rule
core/synthesiser.py       ← Layer 3 — evidence aggregation
output/formatter.py       ← Layer 4 — structured oracle response
main.py                   ← entry point + module registration
tests/test_foundation.py  ← 19 tests, all passing
```

Start from here. Do not rewrite the spine — extend it.
