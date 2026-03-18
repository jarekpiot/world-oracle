# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Production — Fully Operational

Three modules live. PostgreSQL persisting. CI/CD green. Auto-deploying.
Multi-asset visualization with state panel. T0 breaking event agent in progress.
**167 tests passing** across 11 test files.
**Track record:** 4+ oracle calls logged in PostgreSQL.

**Live:** https://world-oracle-production.up.railway.app
**Visual:** https://world-oracle-production.up.railway.app/visual/
**API:** https://world-oracle-production.up.railway.app/api/health
**Repo:** https://github.com/jarekpiot/world-oracle
**CI/CD:** https://github.com/jarekpiot/world-oracle/actions

---

## Architecture

```
GitHub (main) --> GitHub Actions (167 tests) --> Railway (auto-deploy)
                                                   |
                                      PostgreSQL (Railway plugin)
                                                   |
                             FastAPI <-- 3 modules, 15 agents, 10 feeds
                                |
                  /api/query  /api/health  /api/history
                                |
                     /visual/ (breathing visualization + state panel)
                         |
              [OIL] [GAS] [GOLD] [CU] [EUR] [JPY] [BTC] [ETH]
```

---

## What's Built

### Core Spine
- Module Contract (`core/registry.py`) — sacred
- Query Engine, Temporal Engine, Confidence Engine, Synthesiser, Formatter

### Commodities Module (8 agents + T0 breaking in progress)
| Agent | Layer | Feed | Status |
|---|---|---|---|
| price_agent | T0 | EIA Spot | Live |
| **breaking_agent** | **T0** | **GDELT** | **Building — detects missile strikes, explosions, port closures** |
| inventory_agent | T2 | EIA Weekly | Live |
| positioning_agent | T2 | CFTC COT | Live — full CSV parser |
| geopolitical_agent | T1 | GDELT | Live — reads crisis arc pattern |
| weather_agent | T1/T2 | NOAA | Live |
| narrative_agent | T1 | GDELT | Live |
| structural_agent | T3 | Curated | Live |
| shipping_agent | T2 | Baltic Dry | UNKNOWN — needs paid data |

### FX Module (3 agents)
| Agent | Layer | Status |
|---|---|---|
| rate_differential_agent | T2/T3 | Live — EUR/USD, USD/JPY, GBP/USD, USD/CHF |
| flow_agent | T1/T2 | Live — risk-on/risk-off |
| sentiment_agent | T0/T1 | Live |

### Crypto Module (4 agents)
| Agent | Layer | Status |
|---|---|---|
| structural_agent | T3 | Live — BTC, ETH, SOL |
| regulation_agent | T2/T3 | Live — SEC/CFTC/MiCA |
| narrative_agent | T0/T1 | Live |
| onchain_agent | T1 | UNKNOWN — needs Glassnode/Dune |

### Platform
| Component | Status |
|---|---|
| FastAPI Server | Live — 6 endpoints, rate limiting, CORS, root redirect |
| PostgreSQL | Live — Railway plugin, data persists across deploys |
| Signal Store | Async SQLAlchemy — OracleCall + SignalLog tables |
| Feed Monitor | Health checks every 15 min |
| CI/CD | GitHub Actions — tests gate deploy |

### Visualization
| Feature | Status |
|---|---|
| Canvas 2D orbital rings | 5 rings breathing at T3/T2/T1/T0/war frequencies |
| Three.js translucent globe | Wireframe icosahedron with Fresnel glow |
| Signal nodes | 15 orbiting dots with halos and particle sparks |
| State panel (Option B) | Direction, confidence, band, alignment, thesis |
| Signal breakdown | Grouped by T3/T2/T1/T0 with confidence bars |
| Risk section | Invalidators + devil's advocate |
| **Multi-asset selector** | **OIL, GAS, GOLD, CU, EUR, JPY, BTC, ETH** |
| Scroll zoom | 0.4x to 1.6x — fits any screen |
| Mode controls | live / war mode / full align / pause |
| Mock data fallback | Renders immediately, live data replaces async |
| LIVE/MOCK badge | Shows data source |

---

## War / Event Temporal Model
| What happened | Layer | Why |
|---|---|---|
| "Missile hit terminal 3 min ago" | T0 | The flash — breaking_agent |
| "Is this escalation or one-off?" | T1 | Narrative — geopolitical_agent |
| "Middle East in escalation phase" | T2 | Crisis arc — geopolitical_agent |
| "Region permanently unstable" | T3 | Structural — structural_agent |

The explosion is T0. Its meaning propagates upward through all layers.

---

## Database
- PostgreSQL on Railway — `postgres.railway.internal:5432/railway`
- DATABASE_URL injected into API service
- Tables auto-created on startup (OracleCall + SignalLog)
- Track record persists permanently across deploys

---

## Test Coverage: 167 passing
| File | Count | Covers |
|---|---|---|
| test_foundation.py | 19 | Spine |
| test_commodities.py | 18 | Feeds + module contract |
| test_agents.py | 22 | All commodity agents |
| test_price_agent.py | 9 | T0 price |
| test_cot_parser.py | 18 | CFTC COT parser |
| test_fx.py | 20 | FX module |
| test_crypto.py | 31 | Crypto module |
| test_api.py | 10 | FastAPI endpoints |
| test_signal_store.py | 9 | Async persistence |
| test_feed_monitor.py | 5 | Health checks |
| test_dashboard.py | 3 | Dashboard + visual |
| **Total** | **167** | |

---

## What's NOT Built Yet
| Item | Priority | Notes |
|---|---|---|
| T0 breaking event agent | In progress | Detects explosions, strikes, seizures |
| Baltic Dry feed | Medium | Needs paid data provider |
| Crypto onchain feed | Medium | Needs Glassnode/Dune |
| Equities Module | Next | Same contract, new domain |
| Alembic migrations | Low | Tables auto-create for now |
| GDELT rate limiting | Low | Getting 429s — need throttling |

---

## How to Run
```bash
DATABASE_URL=sqlite+aiosqlite:///test.db python -m pytest tests/ -v
python main.py --query "Will crude oil prices rise over the next 6 weeks?"
DATABASE_URL=sqlite+aiosqlite:///local.db uvicorn api.server:app --reload --port 8000
streamlit run dashboard/app.py
open dashboard/visual/index.html
```
