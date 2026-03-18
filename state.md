# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Production — Fully Operational

Three modules, 16 agents, PostgreSQL persisting, CI/CD green, auto-deploying.
Multi-asset visualization with state panel, hover details, and pulse intensity.
**177 tests passing** across 11 test files.

**Live:** https://world-oracle-production.up.railway.app
**Visual:** https://world-oracle-production.up.railway.app/visual/
**API:** https://world-oracle-production.up.railway.app/api/health
**Repo:** https://github.com/jarekpiot/world-oracle
**CI/CD:** https://github.com/jarekpiot/world-oracle/actions

---

## Architecture

```
GitHub (main) --> GitHub Actions (177 tests) --> Railway (auto-deploy)
                                                   |
                                      PostgreSQL (Railway plugin)
                                                   |
                             FastAPI <-- 3 modules, 16 agents, 10 feeds
                                |
                  /api/query  /api/health  /api/history
                                |
                     /visual/ (breathing visualization + state panel)
                         |
              [OIL] [GAS] [GOLD] [CU] [EUR] [JPY] [BTC] [ETH]
```

---

## Modules & Agents

### Commodities (9 agents)
| Agent | Layer | Feed | Status |
|---|---|---|---|
| price_agent | T0 | EIA Spot | Live |
| breaking_agent | T0 | GDELT | Live — explosions, strikes, port closures |
| inventory_agent | T2 | EIA Weekly | Live |
| positioning_agent | T2 | CFTC COT | Live — full CSV parser |
| geopolitical_agent | T1 | GDELT | Live — crisis arc pattern |
| weather_agent | T1/T2 | NOAA | Live |
| narrative_agent | T1 | GDELT | Live |
| structural_agent | T3 | Curated | Live |
| shipping_agent | T2 | Baltic Dry | UNKNOWN — needs paid data |

### FX (3 agents)
| Agent | Layer | Status |
|---|---|---|
| rate_differential_agent | T2/T3 | Live — EUR/USD, USD/JPY, GBP/USD, USD/CHF |
| flow_agent | T1/T2 | Live — risk-on/risk-off |
| sentiment_agent | T0/T1 | Live |

### Crypto (4 agents)
| Agent | Layer | Status |
|---|---|---|
| structural_agent | T3 | Live — BTC, ETH, SOL |
| regulation_agent | T2/T3 | Live — SEC/CFTC/MiCA |
| narrative_agent | T0/T1 | Live |
| onchain_agent | T1 | UNKNOWN — needs Glassnode/Dune |

---

## Platform

| Component | Status |
|---|---|
| FastAPI Server | Live — 6 endpoints, rate limiting, CORS, root redirect to /visual/ |
| PostgreSQL | Live — Railway plugin, persists across deploys |
| Signal Store | Async SQLAlchemy — OracleCall + SignalLog tables |
| Feed Monitor | Health checks every 15 min |
| CI/CD | GitHub Actions — 177 tests gate every deploy |
| GDELT Rate Limiting | Fixed — shared 15min query cache + exponential backoff (2s/4s/8s) |

---

## Visualization

| Feature | Status | Confirmed |
|---|---|---|
| Canvas 2D orbital rings | 5 rings breathing at temporal frequencies | Yes |
| Three.js translucent globe | Wireframe icosahedron + Fresnel glow | Yes |
| Signal nodes | 15 orbiting dots with halos and sparks | Yes |
| **State panel (Option B)** | Direction, confidence, band, thesis, signals, risk | Yes |
| **Multi-asset selector** | OIL, GAS, GOLD, CU, EUR, JPY, BTC, ETH | Yes |
| **Sliding panel** | Click arrow to collapse/expand, viz fills screen | Yes — Playwright verified |
| **Hover detail popup** | Reasoning + decay triggers on signal mouseenter | Yes — Playwright verified |
| **Pulse intensity** | Halo size + spark rate scale with confidence | Yes — code verified |
| Scroll zoom | 0.4x to 1.6x — rings fit any screen | Yes |
| War mode | Red globe, fragmented ring, red bleed | Yes |
| Full align mode | Golden corona, synced pulse | Yes |
| Mock data fallback | Renders immediately, live replaces async | Yes |
| LIVE/MOCK badge | Shows data source | Yes |

---

## War / Event Temporal Model
| What happened | Layer | Agent |
|---|---|---|
| Missile hit terminal 3 min ago | T0 | breaking_agent |
| Is this escalation or one-off? | T1 | geopolitical_agent |
| Middle East in escalation phase | T2 | geopolitical_agent |
| Region permanently unstable | T3 | structural_agent |

---

## GDELT Rate Limiting (Fixed)
- **Problem:** 429 Too Many Requests from multiple agents hitting GDELT simultaneously
- **Fix:** Shared query-level cache (`_GDELT_CACHE`) with 15-minute TTL
- **Backoff:** 3 retries at 2s, 4s, 8s on 429 errors
- **Global rate limit:** Minimum 2s between any GDELT request
- **Affects:** geopolitical_agent, narrative_agent, breaking_agent, crypto narrative, crypto regulation

---

## Test Coverage: 177 passing
| File | Count | Covers |
|---|---|---|
| test_foundation.py | 19 | Spine |
| test_commodities.py | 18 | Feeds + module contract |
| test_agents.py | 31 | All 9 commodity agents incl. T0 breaking |
| test_price_agent.py | 9 | T0 price |
| test_cot_parser.py | 18 | CFTC COT parser |
| test_fx.py | 20 | FX module |
| test_crypto.py | 31 | Crypto module |
| test_api.py | 10 | FastAPI endpoints |
| test_signal_store.py | 9 | Async persistence |
| test_feed_monitor.py | 5 | Health checks |
| test_dashboard.py | 3 | Dashboard + visual |
| **Total** | **177** | |

---

## What's NOT Built Yet
| Item | Priority | Notes |
|---|---|---|
| Live API data in panel | High | Panel shows MOCK — parseAPIResponse needs signal format fix |
| Baltic Dry feed | Medium | Needs paid data provider |
| Crypto onchain feed | Medium | Needs Glassnode/Dune |
| Equities Module | Next | Same contract, new domain |
| Alembic migrations | Low | Tables auto-create for now |

---

## How to Run
```bash
DATABASE_URL=sqlite+aiosqlite:///test.db python -m pytest tests/ -v
python main.py --query "Will crude oil prices rise over the next 6 weeks?"
DATABASE_URL=sqlite+aiosqlite:///local.db uvicorn api.server:app --reload --port 8000
open dashboard/visual/index.html
```
