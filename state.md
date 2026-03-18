# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Production — Fully Operational

Three modules live. PostgreSQL persisting. CI/CD green. Auto-deploying.
**167 tests passing** across 11 test files.
**Track record:** 4 oracle calls logged in PostgreSQL, surviving across deploys.

**Live API:** https://world-oracle-production.up.railway.app
**Visualization:** https://world-oracle-production.up.railway.app/visual/
**Repo:** https://github.com/jarekpiot/world-oracle
**CI/CD:** https://github.com/jarekpiot/world-oracle/actions

---

## Architecture

```
GitHub (main) --push--> GitHub Actions (167 tests) --pass--> Railway (auto-deploy)
                                                               |
                                              PostgreSQL (Railway plugin — persistent)
                                                               |
                                    FastAPI <-- 3 modules, 15 agents, 10 feeds
                                       |
                            /api/query  /api/health  /api/history  /visual/
```

---

## Infrastructure — All Connected

| Component | Status |
|---|---|
| Railway API service | Live — `world-oracle-production.up.railway.app` |
| Railway PostgreSQL plugin | Live — `postgres.railway.internal:5432/railway` |
| DATABASE_URL injected | Done — app auto-detects PostgreSQL |
| Tables auto-created | Done — OracleCall + SignalLog |
| CI/CD pipeline | Green — GitHub Actions tests gate every deploy |
| GitHub secrets | Set — ANTHROPIC_API_KEY, EIA_API_KEY, RAILWAY_TOKEN |
| CORS | Enabled — visualization works from file:// and served |

---

## What's Built

### Core Spine (Phase 1)
| Component | File | Status |
|---|---|---|
| Module Contract | `core/registry.py` | Sacred — do not change without team agreement |
| Query Engine | `core/query_engine.py` | Layer 1 — LLM decomposition + DAG |
| Temporal Engine | `core/temporal_engine.py` | T0-T3 signal lifecycle + decay |
| Confidence Engine | `core/confidence_engine.py` | Scoring + abstain rule |
| Synthesiser | `core/synthesiser.py` | Layer 3 — evidence aggregation |
| Formatter | `output/formatter.py` | Layer 4 — structured output |

### Oracle Team — Commodities Module (8 agents)
| Agent | Layer | Feed | Status |
|---|---|---|---|
| price_agent | T0 | EIA Spot | Live |
| inventory_agent | T2 | EIA Weekly | Live |
| geopolitical_agent | T1 | GDELT | Live |
| weather_agent | T1/T2 | NOAA | Live |
| narrative_agent | T1 | GDELT | Live |
| structural_agent | T3 | Curated | Live |
| positioning_agent | T2 | CFTC COT | Live — full CSV parser |
| shipping_agent | T2 | Baltic Dry | UNKNOWN — needs paid data |

### Oracle Team — FX Module (3 agents)
| Agent | Layer | Feed | Status |
|---|---|---|---|
| rate_differential_agent | T2/T3 | Curated | Live — EUR/USD, USD/JPY, GBP/USD, USD/CHF |
| flow_agent | T1/T2 | GDELT | Live — risk-on/risk-off |
| sentiment_agent | T0/T1 | GDELT | Live |

### Oracle Team — Crypto Module (4 agents)
| Agent | Layer | Feed | Status |
|---|---|---|---|
| onchain_agent | T1 | (pending) | UNKNOWN — needs Glassnode/Dune |
| narrative_agent | T0/T1 | GDELT | Live |
| structural_agent | T3 | Curated | Live — BTC, ETH, SOL |
| regulation_agent | T2/T3 | GDELT | Live — SEC/CFTC/MiCA |

### Build Team — Platform
| Component | File | Status |
|---|---|---|
| FastAPI Server | `api/server.py` | Live — 6 endpoints, rate limiting, CORS |
| Database Models | `db/models.py` | SQLAlchemy 2.0 — OracleCall + SignalLog |
| Async Engine | `db/engine.py` | Auto-detects PostgreSQL vs SQLite |
| Signal Store | `db/signal_store.py` | Fully async — logs calls + individual signals |
| Feed Monitor | `core/feed_monitor.py` | Health checks every 15 min |
| CI/CD | `.github/workflows/deploy.yml` | Tests gate deploy, auto-deploys to Railway |

### Visual Engineer
| Feature | Status |
|---|---|
| 3D WebGL Globe (globe.gl) | Blue Marble + topology + atmosphere |
| Signal Nodes | Glowing dots at 15 real lat/lng locations |
| Arc Flows | Animated arcs from agents to oracle core |
| Ripple Rings | Pulsing at T0/T1/T2/T3 temporal speed |
| Orbital Torus Rings | 4 rings breathing at temporal frequencies |
| Fresnel GLSL Glow | Color shifts: gold/blue/red/dim per state |
| GSAP Breathing | Cardiac rhythm T0, sine T1-T3 |
| Tone.js Audio | Optional soundscape |
| Mode Controls | live / war mode / full align / pause / sound |

---

## Database — PostgreSQL (Live)

| Item | Status |
|---|---|
| Railway PostgreSQL plugin | Live — `postgres.railway.internal:5432/railway` |
| DATABASE_URL on API service | Set — auto-detected by engine |
| SQLAlchemy async models | Done — `db/models.py` |
| Async engine + sessions | Done — `db/engine.py` |
| Signal store async | Done — `db/signal_store.py` |
| Tables auto-created | Done — OracleCall + SignalLog |
| Signal logging per agent | Done — each agent's signal logged individually |
| Data persists across deploys | Verified — 4 calls surviving |
| Old SQLite data | Lost — Railway ephemeral filesystem wiped it pre-migration |

---

## Track Record (PostgreSQL)

```
Total calls:  4
Responded:    4
Abstained:    0
Scored:       0 (no outcomes recorded yet)
Win rate:     N/A

All calls: BEARISH on crude oil, confidence 0.736, alignment 0.667
Track record starts fresh from PostgreSQL migration.
```

---

## Deployment
| Target | URL | Status |
|---|---|---|
| Railway API | https://world-oracle-production.up.railway.app | Live |
| Railway PostgreSQL | postgres.railway.internal:5432 | Live |
| Visualization | https://world-oracle-production.up.railway.app/visual/ | Live |
| GitHub | https://github.com/jarekpiot/world-oracle | Pushed |
| CI/CD | GitHub Actions | Green — tests gate deploy |

---

## Test Coverage
| Test File | Count | Covers |
|---|---|---|
| `test_foundation.py` | 19 | Spine — temporal, confidence, registry, formatter |
| `test_commodities.py` | 18 | Feeds + inventory agent + module contract |
| `test_agents.py` | 22 | All 8 commodity agents incl. T0 price |
| `test_price_agent.py` | 9 | T0 heartbeat — price direction, thresholds |
| `test_cot_parser.py` | 18 | CFTC COT parser + positioning agent |
| `test_fx.py` | 20 | FX module — 3 agents, flow, sentiment |
| `test_crypto.py` | 31 | Crypto module — 4 agents, regulation, onchain |
| `test_api.py` | 10 | FastAPI endpoints + rate limiter |
| `test_signal_store.py` | 9 | Async persistence, history, outcomes, track record |
| `test_feed_monitor.py` | 5 | Health check aggregation + summary |
| `test_dashboard.py` | 3 | Dashboard structure + visual HTML |
| **Total** | **167** | **All passing** |

---

## Temporal Layer Coverage
| Layer | Commodity Agents | FX Agents | Crypto Agents |
|---|---|---|---|
| T3 Slow | structural | rate_differential | structural |
| T2 Regular | inventory, positioning, (shipping) | rate_differential, flow | regulation |
| T1 Quick | geopolitical, weather, narrative | flow, sentiment | narrative, (onchain) |
| T0 Heartbeat | price | sentiment | narrative |

---

## What's NOT Built Yet
| Item | Priority | Notes |
|---|---|---|
| Baltic Dry data | Medium | No free API — needs paid provider |
| Crypto onchain feed | Medium | Needs Glassnode/Dune/CryptoQuant |
| Equities Module | Next | Same contract, new domain prefix |
| Alembic migrations | Low | Tables auto-create; Alembic for schema changes |
| GDELT rate limiting | Low | Getting 429s — need request throttling or caching |

---

## How to Run
```bash
# Tests (167 passing)
DATABASE_URL=sqlite+aiosqlite:///test.db python -m pytest tests/ -v

# CLI
python main.py --query "Will crude oil prices rise over the next 6 weeks?"

# API server (local)
DATABASE_URL=sqlite+aiosqlite:///local.db uvicorn api.server:app --reload --port 8000

# Dashboard
streamlit run dashboard/app.py

# Visualization (standalone)
open dashboard/visual/index.html
```

## Environment Variables
```bash
# Production (all set on Railway)
ANTHROPIC_API_KEY=sk-ant-...     # set in Railway vars
EIA_API_KEY=...                   # set in Railway vars
DATABASE_URL=postgresql://...     # injected by Railway PostgreSQL plugin

# Local dev
DATABASE_URL=sqlite+aiosqlite:///local_dev.db
```
