# World Oracle — Project State
**Last updated:** 2026-03-18

---

## Status: Production — FULLY LIVE

Three modules, 16 agents, all systems operational.
API responding with real oracle data. Visualization shows LIVE badge.
**191 tests passing.** PostgreSQL persisting. CI/CD green.

**Live:** https://world-oracle-production.up.railway.app
**Visual:** https://world-oracle-production.up.railway.app/visual/
**API:** https://world-oracle-production.up.railway.app/api/query
**Repo:** https://github.com/jarekpiot/world-oracle
**CI/CD:** https://github.com/jarekpiot/world-oracle/actions

---

## Latest Oracle Response (live, 2026-03-18)

```
Direction:  NEUTRAL (genuinely conflicted)
Confidence: 0.677
Alignment:  0.667
Thesis:     "Extreme short positioning vs persistent inventory builds = standoff"

T3 structural:  NEUTRAL  0.55  — energy transition uncertainty
T2 strategic:   BEARISH  0.53  — +3.8M build (4th consecutive), geopolitical calm
T2 positioning: BULLISH  0.68  — managed money extremely short (-28,145 contracts)
T1 tactical:    BULLISH  0.55  — cold snap, narrative balanced
T0 heartbeat:   BULLISH  0.48  — WTI $94.65 +4.28%

Key conflict: positioning_agent (bullish 0.68) vs inventory_agent (bearish 0.68)
              — same horizon, opposite directions, equal confidence. True standoff.
```

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

## Data Feeds: 8/10 Live

| Feed | Status |
|---|---|
| EIA Spot Price | Live — filtered correctly (duoarea=NUS, process=SAX) |
| EIA Weekly Petroleum | Live — +3.8M build (was +856M before fix) |
| GDELT Geopolitical | Live — shared 15min cache + backoff |
| NOAA Weather | Live — cold snap detected |
| CFTC COT | Live — parser fixed, showing -28,145 managed money net short |
| GDELT FX / Crypto x2 | Live — shared cache |
| Baltic Dry | Not connected — needs paid provider |
| Crypto Onchain | Not built — needs Glassnode/Dune |

---

## Modules & Agents

### Commodities (9 agents)
| Agent | Layer | Intelligence | Status |
|---|---|---|---|
| price_agent | T0 | Threshold | Live — $94.65 +4.28% |
| breaking_agent | T0 | GDELT volume spike | Live |
| inventory_agent | T2 | **LLM reasoning (Claude)** + fallback | Live — +3.8M build, 4th consecutive |
| positioning_agent | T2 | Extreme detection | Live — managed money -28,145 short |
| geopolitical_agent | T1 | Escalation scoring | Live — calm, no risk premium |
| weather_agent | T1/T2 | Weather impact | Live — cold snap active |
| narrative_agent | T1 | Tone + volume | Live |
| structural_agent | T3 | Curated views | Live |
| shipping_agent | T2 | — | UNKNOWN (needs paid data) |

### FX (3 agents) — all live
### Crypto (4 agents) — 3 live, 1 UNKNOWN (onchain)

---

## Visualization

| Feature | Desktop | Mobile |
|---|---|---|
| Canvas 2D orbital rings | Yes | Yes |
| Three.js translucent globe | Yes | Yes |
| Orb-panel sync (live data) | Yes | Yes |
| State panel with signal breakdown | Yes | Yes (stacks below) |
| Multi-asset selector (8 assets) | Yes | Yes |
| Panel collapse (orb fills space) | Side arrow | Drag handle bar |
| Hover detail popup | Yes | Hidden (too small) |
| Pulse intensity (confidence) | Yes | Yes |
| Zoom | Scroll wheel | Pinch-to-zoom |
| LIVE/MOCK badge | Yes | Yes |

---

## Bugs Fixed This Session (8 total)

1. EIA comparing wrong series (+856M → +3.8M)
2. CFTC COT no-header CSV → manual column parser
3. GDELT 429 rate limiting → shared cache + backoff
4. NOAA 400 → title-case severity params
5. globe.gl crash → replaced with Canvas 2D
6. Panel MOCK data → parseAPIResponse rewritten for real API shape
7. Orb not synced → syncNodesToLiveData()
8. Mobile floating arrow → drag handle bar

---

## Test Coverage: 191 passing

| File | Count |
|---|---|
| test_foundation.py | 19 |
| test_commodities.py | 32 |
| test_agents.py | 31 |
| test_price_agent.py | 9 |
| test_cot_parser.py | 18 |
| test_fx.py | 20 |
| test_crypto.py | 31 |
| test_api.py | 10 |
| test_signal_store.py | 9 |
| test_feed_monitor.py | 5 |
| test_dashboard.py | 3 |
| **Total** | **191** |

---

## What's NOT Built Yet

| Item | Priority | Notes |
|---|---|---|
| LLM reasoning for all agents | High | Only inventory has it — pattern ready |
| Baltic Dry feed | Medium | Needs paid provider |
| Crypto onchain feed | Medium | Needs Glassnode/Dune |
| Equities Module | Next | Same contract |
| Alembic migrations | Low | Tables auto-create |

---

## How to Run

```bash
DATABASE_URL=sqlite+aiosqlite:///test.db python -m pytest tests/ -v
python main.py --query "Will crude oil prices rise?"
DATABASE_URL=sqlite+aiosqlite:///local.db uvicorn api.server:app --reload --port 8000
open dashboard/visual/index.html
```
