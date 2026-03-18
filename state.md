# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Phase 2 Complete (Build + Oracle)

All foundation, oracle, and build team deliverables are implemented and tested.
**86 tests passing** across 7 test files.

---

## What's Built

### Core Spine (Phase 1 — DONE)
| Component | File | Status |
|---|---|---|
| Module Contract | `core/registry.py` | ✅ Sacred — do not change without team agreement |
| Query Engine | `core/query_engine.py` | ✅ Layer 1 — LLM decomposition + DAG |
| Temporal Engine | `core/temporal_engine.py` | ✅ T0–T3 signal lifecycle + decay |
| Confidence Engine | `core/confidence_engine.py` | ✅ Scoring + abstain rule |
| Synthesiser | `core/synthesiser.py` | ✅ Layer 3 — evidence aggregation |
| Formatter | `output/formatter.py` | ✅ Layer 4 — structured output |
| Entry Point | `main.py` | ✅ CLI interface |

### Oracle Team — Commodities Module (Phase 2 — DONE)
| Agent | File | Layer | Feed | Status |
|---|---|---|---|---|
| Inventory | `modules/commodities/agents/inventory_agent.py` | T2 | EIA | ✅ Live (needs API key) |
| Geopolitical | `modules/commodities/agents/geopolitical_agent.py` | T1 | GDELT | ✅ Live (free, no key) |
| Weather | `modules/commodities/agents/weather_agent.py` | T1/T2 | NOAA | ✅ Live (free, no key) |
| Narrative | `modules/commodities/agents/narrative_agent.py` | T1 | GDELT | ✅ Live (free, no key) |
| Structural | `modules/commodities/agents/structural_agent.py` | T3 | Curated | ✅ Live (no feed needed) |
| Shipping | `modules/commodities/agents/shipping_agent.py` | T2 | Baltic Dry | ⏳ Returns UNKNOWN — needs paid data source |
| Positioning | `modules/commodities/agents/positioning_agent.py` | T2 | CFTC COT | ⏳ Returns UNKNOWN — needs CFTC parser |

**5 agents producing real signals, 2 honestly returning UNKNOWN (ZERO FABRICATION).**

### Build Team (Phase 2 — DONE)
| Component | File | Status |
|---|---|---|
| FastAPI Server | `api/server.py` | ✅ 4 endpoints + rate limiting (60/min) |
| Signal Store | `db/signal_store.py` | ✅ SQLite — logs calls, outcomes, track record |
| Feed Monitor | `core/feed_monitor.py` | ✅ Health checks every 15 min |

**API Endpoints:**
- `POST /api/query` — run oracle query (abstain = 200, not 4xx)
- `GET /api/health` — module + feed health
- `GET /api/modules` — registered modules
- `GET /api/history` — past calls + track record
- `GET /api/history/{id}` — single call detail
- `POST /api/history/{id}/outcome` — record market verdict

### Dashboard (Phase 3 — DONE)
| Page | Description | Status |
|---|---|---|
| Live Oracle | Run queries, see full response with reasoning trace | ✅ |
| Signal History | Past calls, outcomes, win rate tracking | ✅ |
| Feed Health | Live/stale feed status per module | ✅ |
| Breathing Map | T3→T0 visual with signal state per layer | ✅ |

---

## Test Coverage
| Test File | Count | Covers |
|---|---|---|
| `test_foundation.py` | 19 | Spine — temporal, confidence, registry, formatter |
| `test_commodities.py` | 18 | Feeds + inventory agent + module contract |
| `test_agents.py` | 22 | All 7 agents — direction, confidence, ZERO FABRICATION |
| `test_api.py` | 10 | FastAPI endpoints + rate limiter |
| `test_signal_store.py` | 9 | Persistence, history, outcomes, track record |
| `test_feed_monitor.py` | 5 | Health check aggregation + summary |
| `test_dashboard.py` | 3 | Dashboard structure + imports |
| **Total** | **86** | **All passing** |

---

## Temporal Layer Coverage
| Layer | Agents | Status |
|---|---|---|
| T3 — Slow Breath | structural_agent | ✅ Curated secular views |
| T2 — Regular Breath | inventory_agent, shipping_agent, positioning_agent | ✅ (2 of 3 live) |
| T1 — Quick Breath | geopolitical_agent, weather_agent, narrative_agent | ✅ All live |
| T0 — Heartbeat | (none) | ❌ Needs live price feed |

---

## What's NOT Built Yet
| Item | Priority | Notes |
|---|---|---|
| T0 live price feed | High | No realtime price agent — need exchange/broker API |
| CFTC COT parser | Medium | Fixed-width text format — needs custom parser |
| Baltic Dry data | Medium | No free API — needs paid provider or scraper |
| FX Module (`modules/fx/`) | Next | Same contract, new domain prefix |
| Crypto Module (`modules/crypto/`) | Later | Same contract, new domain prefix |
| Equities Module (`modules/equities/`) | Later | Same contract, new domain prefix |
| Dockerfile | Low | Containerisation for deployment |
| `.env.example` | Low | Document required env vars |
| Git init + remote | Low | Repo not yet initialised |

---

## How to Run
```bash
# Tests
python -m pytest tests/ -v

# CLI
python main.py --query "Will crude oil prices rise over the next 6 weeks?"

# API server
uvicorn api.server:app --reload --port 8000

# Dashboard
streamlit run dashboard/app.py
```

## Environment Variables Needed
```bash
ANTHROPIC_API_KEY=sk-ant-...     # required for LLM calls
EIA_API_KEY=...                   # free at eia.gov — needed for inventory agent
DATABASE_URL=sqlite:///world_oracle.db  # optional, defaults to local file
```
