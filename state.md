# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Phase 3+ Complete — Live in Production

All phases delivered. Three modules live. CI/CD pipeline active. Deployed to Railway.
**167 tests passing** across 11 test files.

**Live API:** https://world-oracle-production.up.railway.app
**Repo:** https://github.com/jarekpiot/world-oracle

---

## What's Built

### Core Spine (Phase 1 — DONE)
| Component | File | Status |
|---|---|---|
| Module Contract | `core/registry.py` | Sacred — do not change without team agreement |
| Query Engine | `core/query_engine.py` | Layer 1 — LLM decomposition + DAG |
| Temporal Engine | `core/temporal_engine.py` | T0-T3 signal lifecycle + decay |
| Confidence Engine | `core/confidence_engine.py` | Scoring + abstain rule |
| Synthesiser | `core/synthesiser.py` | Layer 3 — evidence aggregation |
| Formatter | `output/formatter.py` | Layer 4 — structured output |
| Entry Point | `main.py` | CLI interface |

### Oracle Team — Commodities Module (DONE — 8 agents)
| Agent | File | Layer | Feed | Status |
|---|---|---|---|---|
| Price | `modules/commodities/agents/price_agent.py` | T0 | EIA Spot | Live (needs API key) |
| Inventory | `modules/commodities/agents/inventory_agent.py` | T2 | EIA Weekly | Live (needs API key) |
| Geopolitical | `modules/commodities/agents/geopolitical_agent.py` | T1 | GDELT | Live (free, no key) |
| Weather | `modules/commodities/agents/weather_agent.py` | T1/T2 | NOAA | Live (free, no key) |
| Narrative | `modules/commodities/agents/narrative_agent.py` | T1 | GDELT | Live (free, no key) |
| Structural | `modules/commodities/agents/structural_agent.py` | T3 | Curated | Live (no feed needed) |
| Shipping | `modules/commodities/agents/shipping_agent.py` | T2 | Baltic Dry | Returns UNKNOWN — needs paid data |
| Positioning | `modules/commodities/agents/positioning_agent.py` | T2 | CFTC COT | Live — real CFTC data parsed |

**7 agents producing real signals, 1 honestly returning UNKNOWN (ZERO FABRICATION).**

### Oracle Team — FX Module (DONE — 3 agents)
| Agent | File | Layer | Feed | Status |
|---|---|---|---|---|
| Rate Differential | `modules/fx/agents/rate_differential_agent.py` | T2/T3 | Curated | Live — EUR/USD, USD/JPY, GBP/USD, USD/CHF |
| Flow | `modules/fx/agents/flow_agent.py` | T1/T2 | GDELT | Live — risk-on/risk-off flows |
| Sentiment | `modules/fx/agents/sentiment_agent.py` | T0/T1 | GDELT | Live — FX narrative momentum |

### Oracle Team — Crypto Module (DONE — 4 agents)
| Agent | File | Layer | Feed | Status |
|---|---|---|---|---|
| Onchain | `modules/crypto/agents/onchain_agent.py` | T1 | (pending) | Returns UNKNOWN — needs Glassnode/Dune |
| Narrative | `modules/crypto/agents/narrative_agent.py` | T0/T1 | GDELT | Live |
| Structural | `modules/crypto/agents/structural_agent.py` | T3 | Curated | Live — BTC, ETH, SOL views |
| Regulation | `modules/crypto/agents/regulation_agent.py` | T2/T3 | GDELT | Live — SEC/CFTC/MiCA signals |

### Build Team (Phase 2 — DONE)
| Component | File | Status |
|---|---|---|
| FastAPI Server | `api/server.py` | Live on Railway — 6 endpoints + rate limiting |
| Signal Store | `db/signal_store.py` | SQLite — logs calls, outcomes, track record |
| Feed Monitor | `core/feed_monitor.py` | Health checks every 15 min |

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
| Live Oracle | Run queries, see full response with reasoning trace | Done |
| Signal History | Past calls, outcomes, win rate tracking | Done |
| Feed Health | Live/stale feed status per module | Done |
| Breathing Map | T3->T0 visual with signal state per layer | Done |
| **World Breathing** | 3D globe visualization — globe.gl + Three.js + GSAP | **Done** |

### Visual Engineer (Phase 4 — DONE)
| Feature | Status |
|---|---|
| 3D WebGL Globe (globe.gl) | Live — Blue Marble texture, topology, atmosphere |
| Signal Nodes | Glowing dots at real lat/lng per agent |
| Arc Flows | Animated arcs from signal locations to north pole |
| Ripple Rings | Pulsing at temporal speed per signal |
| Orbital Torus Rings | 4 rings breathing at T3/T2/T1/T0 frequencies |
| Fresnel Atmospheric Glow | GLSL shader, color shifts with oracle state |
| Bloom Effect | Intensity tied to alignment_score |
| GSAP Breathing | Cardiac rhythm for T0, sine for T1-T3 |
| Tone.js Audio | Optional soundscape — 55hz drone + heartbeat kick |
| Live API Connection | Polls /api/health every 30s |
| Mock Data Fallback | Never goes dark — full signal set |
| Mode Controls | live / war mode / full align / pause / sound |
| Served via FastAPI | /visual/ route + standalone file:// |

---

## Deployment
| Target | URL | Status |
|---|---|---|
| Railway API | https://world-oracle-production.up.railway.app | Live |
| GitHub | https://github.com/jarekpiot/world-oracle | Pushed |
| CI/CD | `.github/workflows/deploy.yml` | Tests gate deploy — push to main auto-deploys |

Verified live endpoints:
- `/api/health` — returns module status + feed health
- `/api/modules` — shows commodities.v1 registered
- `/api/query` — end-to-end oracle response with 8 signals
- `/api/history` — tracks all calls with track record

---

## Test Coverage
| Test File | Count | Covers |
|---|---|---|
| `test_foundation.py` | 19 | Spine — temporal, confidence, registry, formatter |
| `test_commodities.py` | 18 | Feeds + inventory agent + module contract |
| `test_agents.py` | 22 | All 8 commodity agents incl. T0 price |
| `test_price_agent.py` | 9 | T0 heartbeat — price direction, thresholds |
| `test_fx.py` | 20 | FX module — 3 agents, flow, sentiment |
| `test_crypto.py` | 31 | Crypto module — 4 agents, regulation, onchain |
| `test_api.py` | 10 | FastAPI endpoints + rate limiter |
| `test_signal_store.py` | 9 | Persistence, history, outcomes, track record |
| `test_feed_monitor.py` | 5 | Health check aggregation + summary |
| `test_cot_parser.py` | 18 | CFTC COT parser + positioning agent |
| `test_dashboard.py` | 3 | Dashboard structure + imports |
| **Total** | **167** | **All passing** |

---

## Temporal Layer Coverage (Commodities)
| Layer | Agents | Status |
|---|---|---|
| T3 — Slow Breath | structural_agent | Curated secular views |
| T2 — Regular Breath | inventory_agent, positioning_agent, shipping_agent | 2 of 3 live, 1 pending feed |
| T1 — Quick Breath | geopolitical_agent, weather_agent, narrative_agent | All live |
| T0 — Heartbeat | price_agent | Live — EIA daily spot price |

**All four temporal layers now covered.**

---

## First Live Oracle Response (2026-03-18)
```
Query:      Will crude oil prices rise over the next 6 weeks?
Direction:  BEARISH
Confidence: 0.786
Alignment:  1.00
Thesis:     Large inventory builds + geopolitical calm removing supply risk premium
Signals:    8 received (7 agents + T0 price)
```

---

## What's NOT Built Yet
| Item | Priority | Notes |
|---|---|---|
| Baltic Dry data | Medium | No free API — needs paid provider or scraper |
| Crypto onchain feed | Medium | Needs Glassnode/Dune/CryptoQuant integration |
| Equities Module | Next | Same contract, new domain prefix |
| Dockerfile | Low | Railway deploys via Nixpacks currently |

---

## How to Run
```bash
# Tests (149 passing)
python -m pytest tests/ -v

# CLI
python main.py --query "Will crude oil prices rise over the next 6 weeks?"

# API server (local)
uvicorn api.server:app --reload --port 8000

# Dashboard
streamlit run dashboard/app.py
```

## Environment Variables
```bash
ANTHROPIC_API_KEY=sk-ant-...     # required for LLM calls
EIA_API_KEY=...                   # free at eia.gov — needed for inventory + price agents
DATABASE_URL=sqlite:///world_oracle.db  # optional, defaults to local file
```
