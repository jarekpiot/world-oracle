# World Oracle — CLAUDE.md
## Shared Project Context

---

## What This Is

The World Oracle is an AI system that reads global markets the way a doctor
reads a patient's breathing — not just the price (the heartbeat) but the deep
rhythms underneath.

The world breathes at four frequencies simultaneously:

```
T3  SLOW BREATH    months → years    structural cycles, secular trends
T2  REGULAR BREATH weeks → months    macro regimes, inventory cycles
T1  QUICK BREATH   hours → days      narrative momentum, positioning
T0  HEARTBEAT      seconds → minutes price, breaking events, flow
```

Every domain of the world maps onto these layers:

```
ENERGY          Oil, gas, LNG, coal, power — the metabolism of civilisation
METALS          Gold, copper, iron ore, lithium — the industrial skeleton
AGRICULTURE     Wheat, corn, soy, sugar — the food layer
TRADE & CAPITAL Dollar cycles, rate regimes, capital flows
WEATHER         Droughts, storms, La Niña/El Niño — nature's breath
GEOPOLITICS     Sanctions, elections, alliances, wars
WAR             The world holding its breath — supply chains freeze, capital flees
NARRATIVE       Sentiment, social, media cycles — how stories move markets
```

The oracle reads ALL of these simultaneously, finds where multiple breathing
cycles align, and tells you where in the cycle the world currently is.

---

## Architecture — Four Layers

```
Query / continuous scan
        │
        ▼
Layer 1 — Query Understanding     core/query_engine.py
  type · domain path · temporal layer · confidence threshold · DAG
        │
        ▼
Layer 2 — Module Registry         core/registry.py
  resolves domain path → routes to correct agent pool
        │
        ├── Commodities Module    modules/commodities/   ← SEED (build first)
        ├── FX Module             modules/fx/            ← v2
        ├── Crypto Module         modules/crypto/        ← v3
        └── Equities Module       modules/equities/      ← v4
        │
        ▼
Layer 3 — Evidence Aggregation    core/synthesiser.py
  temporal alignment · source weighting · devil's advocate · conflict resolution
        │
  [Temporal Engine]               core/temporal_engine.py
  [Confidence Engine]             core/confidence_engine.py
        │
        ▼
Layer 4 — Answer + Output         output/formatter.py
  view · confidence band · T3→T0 trace · invalidators · abstain if unsure
        │
        ▼
Consumer Layer
  dashboard · API · signal engine · trading system
```

---

## The Module Contract

Every asset class module implements this interface (core/registry.py):

```python
async def handle(query: DecomposedQuery) -> ModuleResponse
async def health_check() -> dict
async def decay_check(signal: Signal) -> bool
```

This contract is SACRED. It is the handshake between Build Team and Oracle Team.
Neither team breaks it without a migration plan and explicit sign-off.

---

## The Two Teams

**Build Team** — owns the platform (core/, api/, dashboard/, tests/)
  → Read BUILD_TEAM.md for your directives

**Oracle Team** — owns the intelligence (modules/)
  → Read ORACLE_TEAM.md for your directives

---

## Absolute Rules (both teams)

1. ZERO FABRICATION — if data is unavailable, return low confidence. Never guess.
2. The oracle must be able to ABSTAIN — "insufficient signal" is a valid answer.
3. One LLM call per synthesis — no multiple LLM opinions colliding.
4. Every signal carries: confidence score, temporal layer, decay triggers, reasoning.
5. Tests must pass before any commit to main.
6. The module contract in core/registry.py does not change without team agreement.

---

## Repo Structure

```
world-oracle/
  CLAUDE.md                 ← you are here (shared context)
  BUILD_TEAM.md             ← build team directives
  ORACLE_TEAM.md            ← oracle team directives
  main.py                   ← entry point
  requirements.txt
  core/
    __init__.py
    registry.py             ← THE CONTRACT — handle with care
    query_engine.py         ← Layer 1
    temporal_engine.py      ← signal lifecycle
    confidence_engine.py    ← scoring + abstain
    synthesiser.py          ← Layer 3
  modules/
    __init__.py
    commodities/            ← seed module (Oracle Team)
      __init__.py
      agents/
      feeds/
    fx/                     ← v2
    crypto/                 ← v3
    equities/               ← v4
  output/
    __init__.py
    formatter.py            ← Layer 4
  api/                      ← Build Team
  dashboard/                ← Build Team
  tests/
    test_foundation.py      ← 19 tests, all passing
```

---

## Current Status

- [x] core/registry.py         — module contract + registry
- [x] core/query_engine.py     — Layer 1 decomposition + DAG
- [x] core/temporal_engine.py  — T0–T3 signal lifecycle
- [x] core/confidence_engine.py — scoring + abstain rule
- [x] core/synthesiser.py      — Layer 3 evidence aggregation
- [x] output/formatter.py      — Layer 4 structured output
- [x] main.py                  — entry point
- [x] tests/test_foundation.py — 19/19 passing
- [ ] modules/commodities/     — NEXT: Oracle Team Phase 2
- [ ] api/                     — NEXT: Build Team Phase 2
- [ ] dashboard/               — NEXT: Build Team Phase 3
