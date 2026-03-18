# Project Breathe — Specification & Framework
## Version 1.0 · March 2026
## github.com/jarekpiot/world-oracle

---

## What This Is

A modular AI market intelligence system that reads global markets the way
a doctor reads a patient's breathing — not just the price (heartbeat) but
the deep rhythms underneath.

The system does not predict the next heartbeat.
It tells you WHERE IN THE BREATHING CYCLE the world currently is.
That is the edge.

---

## The Four Temporal Layers — Non-Negotiable Design Principle

Every signal in the system belongs to exactly one layer.
A T1 signal and a T2 signal are NEVER in conflict — they answer different
questions about different time horizons.

```
T3  SLOW BREATH      months → years     structural cycles
T2  REGULAR BREATH   weeks → months     macro cycle — THE SWEET SPOT
T1  QUICK BREATH     hours → days       narrative momentum
T0  HEARTBEAT        seconds → minutes  price and flow
```

### T3 — Structural (what the world is doing over years)
- Energy transition — coal → gas → renewable demand curves
- Dollar supercycle — 7-10 year USD bull/bear cycles
- Commodity supercycle — 20-30 year demand waves
- Geopolitical era shift — multipolar world, de-dollarisation
- Demographic demand — EM urbanisation vs DM ageing

### T2 — Macro Cycle (what the world is doing over weeks/months)
- Inventory cycle — EIA weekly petroleum, LME metals warehouse
- Central bank policy — rate hike/cut cycles
- Geopolitical crisis arc — escalation → stalemate → resolution
- OPEC compliance window — output decisions
- China demand cycle — PMI, restocking, stimulus

### T1 — Narrative (what the world is talking about this week)
- Narrative velocity — is the story accelerating or fading?
- Tanker and shipping flow — AIS data, chokepoints
- COT positioning — speculative vs commercial
- Weather shock — near-term crop/energy stress
- Social sentiment — key account monitoring

### T0 — Heartbeat (what price is doing right now)
- Live spot and futures price
- Order flow and volume
- Breaking news (first 60 seconds)
- Price dislocation vs model view

---

## War — The World Holding Its Breath

War is not just a T1 signal. It has a breathing pattern across all layers:

- Escalation = the inhale → energy spike, risk assets fall
- Stalemate  = held breath → elevated vol, narrative-driven
- Resolution = the exhale → supply routes reopen, risk premium compresses

The system tracks war cycle PHASE, not just whether conflict exists.

---

## Architecture — Four Layers + Module Registry

```
Query / continuous scan
        │
        ▼
Layer 1 — Query Understanding         core/query_engine.py
  type · domain path · temporal layer · confidence threshold · DAG
        │
        ▼
Layer 2 — Module Registry             core/registry.py
  resolves domain path → routes to agent pool
        │
  ┌─────┴──────┬──────────┬────────────┐
  Commodities  FX         Crypto       Equities
  (SEED·live)  (v2·live)  (v3·live)    (v4·planned)
        │
        ▼
Layer 3 — Evidence Aggregation        core/synthesiser.py
  temporal alignment · source weighting · devil's advocate
        │
  [Temporal Engine]    [Confidence Engine]
  decay · validity      score · gate · ABSTAIN
        │
        ▼
Layer 4 — Answer + Output             output/formatter.py
  view · confidence band · T3→T0 trace · invalidators
        │
        ▼
Consumer Layer
  dashboard · FastAPI · signal engine · trading system
```

---

## The Module Contract — Sacred

Every asset class implements these three methods.
BUILD TEAM owns this contract. ORACLE TEAM implements it.
Neither changes it without explicit agreement from both.

```python
class OracleModule(ABC):
    async def handle(query: DecomposedQuery) -> ModuleResponse
    async def health_check() -> dict
    async def decay_check(signal: Signal) -> bool
```

Adding FX, Crypto, Equities = new folder, same interface, core untouched.

---

## The Abstain Rule — Most Important Behavioural Rule

If confidence < threshold → output INSUFFICIENT_SIGNAL, not a guess.

A system that always produces an answer is dangerous.
One that says "don't act" when it isn't sure is trustworthy.

This is the ZERO FABRICATION rule:
- Data unavailable → return UNKNOWN direction, confidence 0.25
- Never extrapolate beyond evidence
- Decay triggers must be SPECIFIC named events, not "market conditions change"

---

## Platform Stack

```
Runtime:     Python 3.11, async throughout (asyncio)
API:         FastAPI + uvicorn
Database:    PostgreSQL on Railway (NOT SQLite — filesystem resets on deploy)
ORM:         SQLAlchemy 2.0 async + asyncpg
Migrations:  Alembic (runs on every deploy before server starts)
Deploy:      Railway — auto-deploy from GitHub main branch
CI/CD:       GitHub Actions — tests gate every deploy
Start cmd:   alembic upgrade head && uvicorn api.server:app --host 0.0.0.0 --port $PORT
```

CRITICAL: SQLite = data loss on every Railway deploy. PostgreSQL only.

---

## Current Build Status (2026-03-18)

Live API: https://world-oracle-production.up.railway.app
Repo:     https://github.com/jarekpiot/world-oracle
Tests:    149 passing across 10 test files

### What's Built
- Core spine (4 layers)                    ✅ 19 tests
- Commodities module (8 agents)            ✅ 40 tests — 6 live, 2 UNKNOWN
- FX module (3 agents)                     ✅ 20 tests
- Crypto module (4 agents)                 ✅ 31 tests — 3 live, 1 UNKNOWN
- FastAPI server (6 endpoints)             ✅ Live on Railway
- Signal store                             ⚠️  SQLite — MUST migrate to PostgreSQL
- Streamlit dashboard (4 pages)            ✅ Including breathing map
- GitHub Actions CI/CD                     ✅ Tests gate Railway deploy
- Visual Engineer (3D globe)               🔄 In progress

### What's NOT Built Yet
- PostgreSQL migration (URGENT)
- CFTC COT parser (positioning_agent T2)
- Baltic Dry feed (shipping_agent T2)
- Crypto onchain feed (Glassnode/Dune)
- Equities module (v4)

---

## Agents — Temporal Layer Coverage

### Commodities
| Agent              | Layer | Feed        | Status              |
|--------------------|-------|-------------|---------------------|
| structural_agent   | T3    | Curated     | Live                |
| inventory_agent    | T2    | EIA Weekly  | Live (needs key)    |
| shipping_agent     | T2    | Baltic Dry  | UNKNOWN (needs data)|
| positioning_agent  | T2    | CFTC COT    | UNKNOWN (needs parser)|
| geopolitical_agent | T1    | GDELT       | Live (free)         |
| weather_agent      | T1/T2 | NOAA        | Live (free)         |
| narrative_agent    | T1    | GDELT       | Live (free)         |
| price_agent        | T0    | EIA Spot    | Live (needs key)    |

### FX
| Agent                    | Layer | Status                    |
|--------------------------|-------|---------------------------|
| rate_differential_agent  | T2/T3 | Live — major pairs        |
| flow_agent               | T1/T2 | Live — risk-on/off flows  |
| sentiment_agent          | T0/T1 | Live — FX narrative       |

### Crypto
| Agent              | Layer | Status                         |
|--------------------|-------|--------------------------------|
| structural_agent   | T3    | Live — BTC, ETH, SOL           |
| regulation_agent   | T2/T3 | Live — SEC/CFTC/MiCA           |
| narrative_agent    | T0/T1 | Live — crypto narrative        |
| onchain_agent      | T1    | UNKNOWN (needs Glassnode/Dune) |

---

## The Two Teams

### Build Team — owns the platform
Files: core/, api/, dashboard/, db/, tests/, .github/
Does NOT touch: modules/

### Oracle Team — owns the intelligence
Files: modules/ only
Does NOT touch: core/, api/, dashboard/

They never block each other because the module contract is stable.

---

## Monetisation (honest assessment)

No ads. The visual is the product. Ads destroy credibility with traders.

- Tier 1 (now–6mo):    Use ourselves on prediction markets → $500–3k/mo
                        Builds track record — required for Tier 2
- Tier 2 (6–18mo):     Signal dashboard SaaS → $300–500/seat → $4k–15k/mo
                        Tommy is customer 1
- Tier 3 (12–30mo):    API / white-label to quant shops → $10k–60k/mo
- Tier 4 (2–4yr):      Institutional → $50k+/mo
                        Edge vs Bloomberg: interpretation not data

---

## Absolute Rules — Both Teams, Always

1. ZERO FABRICATION — unknown data = UNKNOWN direction, never a guess
2. Oracle ABSTAINS when confidence < threshold — INSUFFICIENT_SIGNAL is valid
3. One LLM call per synthesis — no chained reasoning within one agent
4. Every signal: confidence + temporal_layer + decay_triggers + reasoning
5. Tests must pass before any commit to main
6. core/registry.py module contract does not change without team agreement
7. Decay triggers must be SPECIFIC — named events, not vague conditions
8. T0 signals do not override T2 views — different horizons, different questions
9. PostgreSQL only in production — SQLite causes data loss on Railway
10. All database operations must be async — never block the event loop

---

## Signal Locations (for visual — real geography)

| Signal              | Lat    | Lng    |
|---------------------|--------|--------|
| EIA crude (Texas)   | 31.0   | -97.0  |
| Middle East         | 26.0   |  50.0  |
| Red Sea             | 18.0   |  40.0  |
| Strait of Hormuz    | 26.5   |  56.5  |
| Ukraine             | 49.0   |  32.0  |
| Taiwan Strait       | 24.0   | 119.0  |
| LME London          | 51.5   |  -0.1  |
| Chile (copper)      | -30.0  | -71.0  |
| US Crop Belt        | 41.0   | -95.0  |
| OPEC Vienna         | 48.2   |  16.4  |
| New York Fed        | 40.7   | -74.0  |
| ECB Frankfurt       | 50.1   |   8.7  |
| Bank of Japan       | 35.7   | 139.7  |

---

## How to Run

```bash
# Tests
python -m pytest tests/ -v

# CLI
python main.py --query "Will crude oil prices rise over the next 6 weeks?"

# API (local)
uvicorn api.server:app --reload --port 8000

# Dashboard
streamlit run dashboard/app.py
```

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://...   # Railway injects this
EIA_API_KEY=...                         # free at eia.gov
PORT=8000                               # Railway injects this
```
