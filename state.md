# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Production — API credits depleted, feeds live, viz complete

Three modules, 16 agents, PostgreSQL persisting, CI/CD green.
Mobile-responsive visualization with synced orb + state panel.
**191 tests passing** across 11 test files.
**Blocker:** Anthropic API credit balance is empty — /api/query returns 500 until topped up.

**Live:** https://world-oracle-production.up.railway.app
**Visual:** https://world-oracle-production.up.railway.app/visual/
**Repo:** https://github.com/jarekpiot/world-oracle
**CI/CD:** https://github.com/jarekpiot/world-oracle/actions
**Credits:** https://console.anthropic.com/settings/billing

---

## Architecture

```
GitHub (main) --> GitHub Actions (191 tests) --> Railway (auto-deploy)
                                                   |
                                      PostgreSQL (Railway plugin)
                                                   |
                             FastAPI <-- 3 modules, 16 agents, 10 feeds
                                |
                  /api/query  /api/health  /api/history
                                |
                     /visual/ (orb + panel, synced, mobile responsive)
                         |
              [OIL] [GAS] [GOLD] [CU] [EUR] [JPY] [BTC] [ETH]
```

---

## What Works Right Now (no API credits needed)

- `/api/health` — all feed health status
- `/api/modules` — 3 modules registered (commodities, fx, crypto)
- `/api/history` — 188+ oracle calls logged in PostgreSQL
- `/visual/` — full visualization with mock data fallback
- All data feeds pulling live (EIA, GDELT, NOAA, CFTC COT)

## What's Blocked

- `/api/query` — returns 500 (Anthropic credits depleted)
- Visual panel shows MOCK instead of LIVE (query endpoint down)
- Inventory LLM reasoning agent can't reason (falls back to thresholds)

**Fix:** Add credits at https://console.anthropic.com/settings/billing

---

## Modules & Agents

### Commodities (9 agents)
| Agent | Layer | Feed | Intelligence | Status |
|---|---|---|---|---|
| price_agent | T0 | EIA Spot | Threshold | Live |
| breaking_agent | T0 | GDELT | Volume spike detection | Live |
| inventory_agent | T2 | EIA Weekly | **LLM reasoning (Claude)** + threshold fallback | Live — correct data now (+3.8M not +856M) |
| positioning_agent | T2 | CFTC COT | Extreme positioning detection | Live — parser fixed |
| geopolitical_agent | T1 | GDELT | Escalation scoring | Live |
| weather_agent | T1/T2 | NOAA | Weather impact mapping | Live |
| narrative_agent | T1 | GDELT | Tone + volume analysis | Live |
| structural_agent | T3 | Curated | Static views | Live |
| shipping_agent | T2 | Baltic Dry | — | UNKNOWN (needs paid data) |

### FX (3 agents)
| Agent | Layer | Status |
|---|---|---|
| rate_differential_agent | T2/T3 | Live — curated views |
| flow_agent | T1/T2 | Live — GDELT risk-on/off |
| sentiment_agent | T0/T1 | Live — GDELT |

### Crypto (4 agents)
| Agent | Layer | Status |
|---|---|---|
| structural_agent | T3 | Live — BTC, ETH, SOL |
| regulation_agent | T2/T3 | Live — GDELT |
| narrative_agent | T0/T1 | Live — GDELT |
| onchain_agent | T1 | UNKNOWN (needs Glassnode/Dune) |

---

## Data Feeds: 8/10 Live

| Feed | Status | Notes |
|---|---|---|
| EIA Spot Price | Live | Fixed — filters by duoarea=NUS, process=SAX |
| EIA Weekly Petroleum | Live | Fixed — was comparing wrong series (+856M bug) |
| GDELT Geopolitical | Live | Fixed — shared 15min cache + exponential backoff |
| NOAA Weather | Live | Fixed — title-case severity params |
| CFTC COT | Live | Fixed — no-header CSV parsed with column indices |
| GDELT FX | Live | Shared cache with geopolitical |
| GDELT Crypto x2 | Live | Shared cache |
| Baltic Dry | Not connected | Needs paid provider |
| Crypto Onchain | Not built | Needs Glassnode/Dune |

---

## Bugs Fixed This Session

| Bug | Impact | Fix |
|---|---|---|
| EIA comparing different series | Oracle saw +856M barrel build (nonsense) | Filter by duoarea=NUS + process=SAX |
| CFTC COT no header row | Positioning agent always returned UNKNOWN | Use csv.reader with manual column indices |
| GDELT 429 rate limiting | Multiple agents hammering GDELT | Shared query cache (15min) + backoff |
| NOAA 400 error | Weather agent offline | Title-case severity, repeated params |
| globe.gl .animateIn() crash | Visualization blank | Removed invalid method, use Three.js r149 |
| Panel showing MOCK | parseAPIResponse wrong format | Rewritten to match actual API response shape |
| Orb not synced with panel | Nodes were hardcoded mock data | syncNodesToLiveData() rebuilds from API |
| Mobile floating arrow | Toggle stuck in middle of screen | Replaced with drag handle bar |

---

## Visualization

| Feature | Status | Platform |
|---|---|---|
| Canvas 2D orbital rings | Working | Desktop + Mobile |
| Three.js translucent globe | Working | Desktop |
| Orb-panel sync | Working | Both |
| State panel (Option B) | Working | Both |
| Multi-asset selector (8 assets) | Working | Both |
| Sliding panel collapse | Working | Desktop: side arrow, Mobile: drag bar |
| Hover detail popup | Working | Desktop only |
| Pulse intensity (confidence-driven) | Working | Both |
| Scroll zoom / pinch-to-zoom | Working | Desktop: scroll, Mobile: pinch |
| War mode / Full align | Working | Both |
| Mock data fallback | Working | Both |
| Mobile responsive | Working | Stacks vertically, scales controls |

---

## Platform

| Component | Status |
|---|---|
| FastAPI Server | Live — 6 endpoints + root redirect |
| PostgreSQL | Live — Railway plugin, 188+ calls persisted |
| Async SQLAlchemy | Live — OracleCall + SignalLog |
| CI/CD | Green — 191 tests gate deploy |
| CORS | Enabled |
| GDELT Rate Limiting | Fixed — shared cache + backoff |

---

## Test Coverage: 191 passing

| File | Count | Covers |
|---|---|---|
| test_foundation.py | 19 | Spine |
| test_commodities.py | 32 | Feeds + inventory LLM reasoning + module |
| test_agents.py | 31 | All 9 commodity agents + breaking |
| test_price_agent.py | 9 | T0 price |
| test_cot_parser.py | 18 | CFTC COT parser |
| test_fx.py | 20 | FX module |
| test_crypto.py | 31 | Crypto module |
| test_api.py | 10 | FastAPI endpoints |
| test_signal_store.py | 9 | Async persistence |
| test_feed_monitor.py | 5 | Health checks |
| test_dashboard.py | 3 | Dashboard + visual |
| **Total** | **191** | |

---

## What's NOT Built Yet

| Item | Priority | Notes |
|---|---|---|
| **API credits** | **BLOCKER** | Top up at console.anthropic.com |
| LLM reasoning for all agents | High | Only inventory has it — pattern ready for others |
| Baltic Dry feed | Medium | Needs paid provider |
| Crypto onchain feed | Medium | Needs Glassnode/Dune |
| Equities Module | Next | Same contract, new domain |
| Alembic migrations | Low | Tables auto-create |

---

## How to Run

```bash
DATABASE_URL=sqlite+aiosqlite:///test.db python -m pytest tests/ -v
python main.py --query "Will crude oil prices rise over the next 6 weeks?"
DATABASE_URL=sqlite+aiosqlite:///local.db uvicorn api.server:app --reload --port 8000
open dashboard/visual/index.html
```
