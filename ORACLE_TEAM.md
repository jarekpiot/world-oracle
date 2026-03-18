# World Oracle — ORACLE TEAM
## Intelligence & Signal Directives

---

## Your Role

You are the Oracle Team. You own the intelligence — the brain of the oracle.
You build the modules that read the world's breathing cycles.

You do NOT touch core/ or api/ or dashboard/. That is Build Team territory.
Your only contract with Build Team is the OracleModule interface in core/registry.py.
Implement that interface correctly and the spine handles everything else.

---

## The World Breathing — Your Domain Map

The oracle reads the world at four temporal frequencies.
Every signal you produce belongs to exactly one layer:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T3  SLOW BREATH     months → years      the world's deep rhythm
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Energy transition          Coal → gas → renewable demand curves
  Dollar supercycle          7–10 year USD bull/bear cycles
  Commodity supercycle       20–30 year demand waves
  Demographic shifts         Ageing populations, urbanisation
  Geopolitical era shift     Multipolar world, de-dollarisation
  Climate structural change  Crop yield long-run, sea level, drought

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T2  REGULAR BREATH  weeks → months      the macro cycle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Central bank policy cycle  Rate hike/cut cycles
  Inventory cycle            Build → draw → build (EIA, LME)
  Crop season                Planting → growing → harvest
  Geopolitical crisis arc    Escalation → stalemate → resolution
  War cycle phase            Inhale (escalation) → held breath →
                             exhale (ceasefire/exhaustion)
  OPEC policy window         Output decisions, compliance
  Earnings cycle             Quarterly corporate results
  China demand cycle         PMI, restocking, policy stimulus

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T1  QUICK BREATH    hours → days        narrative momentum
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  News narrative momentum    Is a story accelerating or fading?
  Tanker / shipping flow     AIS data, route changes, chokepoints
  Options flow               Large positioning, unusual activity
  COT positioning            Speculative vs commercial positioning
  Weather shock              Hurricane, drought, cold snap (near-term)
  Breaking geopolitical      Missile strike, sanctions announcement
  Social sentiment spike     X/Twitter key accounts, narrative velocity
  EIA/USDA surprise          Bigger draw/build than expected

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T0  HEARTBEAT       seconds → minutes   price and flow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Live price                 Spot, futures, basis
  Order flow                 Bid/ask pressure, volume spikes
  Breaking news              Reuters/Bloomberg wire (first 60 seconds)
  Price dislocation          Oracle model vs market price gap
  Liquidation cascade        Margin calls, forced selling signals
  Real-time AIS anomaly      Tanker stops, unexpected routing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## What You Own

```
modules/
  commodities/           ← BUILD THIS FIRST (seed module)
    __init__.py          ← CommoditiesModule implementing OracleModule
    agents/
      inventory_agent.py      ← T2: EIA stocks, LME warehouse
      weather_agent.py        ← T1/T2: NOAA, crop stress models
      geopolitical_agent.py   ← T1/T2/T3: GDELT, Reuters, war cycle
      shipping_agent.py       ← T1/T2: Baltic Dry, AIS tanker flow
      positioning_agent.py    ← T1/T2: CFTC COT reports
      narrative_agent.py      ← T0/T1: news, social sentiment
      structural_agent.py     ← T3: energy transition, secular demand
    feeds/
      base.py                 ← base HTTP feed class (already built)
      eia.py                  ← EIA API (free, weekly petroleum data)
      lme.py                  ← LME metals warehouse data
      noaa.py                 ← NOAA weather + climate
      cot.py                  ← CFTC commitment of traders (free)
      gdelt.py                ← GDELT geopolitical events (free)
      baltic.py               ← Baltic Dry Index

  fx/                    ← v2 (after commodities validated)
  crypto/                ← v3
  equities/              ← v4
```

---

## Phase 2 — Your Immediate Tasks

### Task O-1: CommoditiesModule skeleton

Create `modules/commodities/__init__.py`:

```python
class CommoditiesModule(OracleModule):
    domain_prefix = "commodity"
    id = "commodities.v1"
    temporal_layers = [T0, T1, T2, T3]
    confidence_range = (0.35, 0.90)
    query_types = [PREDICTIVE, FACTUAL, CAUSAL, COMPARATIVE]

    async def handle(self, query: DecomposedQuery) -> ModuleResponse:
        # Run all agents in parallel (those with no dependencies)
        # Collect signals
        # Return ModuleResponse
```

### Task O-2: inventory_agent.py (start here)

The single most important commodity signal.
An inventory DRAW (stocks falling) = bullish. A BUILD = bearish.

```python
# Connects to: EIA weekly petroleum, LME metals warehouse
# Temporal layer: T2 (weeks → months)
# Confidence range: 0.70 – 0.88 (hard data, high trust)

async def run(domain_path: str, temporal_engine: TemporalEngine) -> Signal:
    # 1. Fetch EIA data
    # 2. Calculate draw/build vs 5-year average
    # 3. Tag signal with T2 layer
    # 4. Return Signal with decay_triggers = ["OPEC surprise output",
    #                                          "SPR release announced",
    #                                          "Major demand shock"]
```

### Task O-3: geopolitical_agent.py

War is the world holding its breath.
This agent reads the war/conflict cycle phase:

```
Escalation  → inhale  → bullish energy, bearish risk assets
Stalemate   → held    → elevated vol, narrative-driven
Resolution  → exhale  → supply routes reopen, risk premium compresses
```

```python
# Connects to: GDELT event database, Reuters headlines
# Temporal layer: T1 (narrative), T2 (crisis arc), T3 (era shift)
# Key regions: Middle East, Ukraine, Taiwan Strait, Hormuz, Red Sea
```

### Task O-4: Remaining agents

Build in this order:
1. inventory_agent.py      ← hard data, highest confidence
2. geopolitical_agent.py   ← war/politics signals
3. weather_agent.py        ← NOAA, crop stress
4. shipping_agent.py       ← Baltic Dry, tanker flow
5. positioning_agent.py    ← CFTC COT
6. narrative_agent.py      ← news + social
7. structural_agent.py     ← T3 secular trends

---

## Agent Rules — Non-Negotiable

### ZERO FABRICATION
If a data feed is unavailable, return the signal with confidence 0.25–0.35
and direction UNKNOWN. Never invent data or extrapolate beyond evidence.

```python
# CORRECT
if not data:
    return temporal_engine.tag_signal(
        direction=SignalDirection.UNKNOWN,
        confidence=0.25,
        reasoning="EIA feed unavailable — no inventory data this cycle"
    )

# WRONG — never do this
return temporal_engine.tag_signal(
    direction=SignalDirection.BULLISH,
    confidence=0.65,
    reasoning="Assuming bullish based on recent trends"  # fabrication
)
```

### One LLM call per agent
Each agent may make exactly ONE LLM call for its reasoning step.
No chained prompts within a single agent. Save LLM calls for synthesis.

### Decay triggers must be specific
Every signal must list 2–4 specific events that would kill it.

```python
# CORRECT — specific
decay_triggers = [
    "OPEC announces output increase >500k bpd",
    "China PMI falls below 48",
    "US SPR release >20m barrels announced",
    "Ceasefire agreement in key producing region"
]

# WRONG — vague
decay_triggers = ["market conditions change", "new data released"]
```

### Temporal layer must be accurate
Assign the layer that matches the signal's real horizon:

```
T0 — price right now, breaking event in last hour
T1 — narrative over next 48 hours, positioning this week
T2 — cycle view over next 4–12 weeks
T3 — structural thesis over next 12–36 months
```

---

## Data Feeds — All Free

| Feed | Source | Refresh | Layer | API Key |
|---|---|---|---|---|
| EIA petroleum | api.eia.gov | Weekly Wed | T2 | Free signup |
| CFTC COT | cftc.gov | Weekly Fri | T1/T2 | No key needed |
| GDELT events | api.gdeltproject.org | 15 min | T1 | No key needed |
| NOAA weather | api.weather.gov | 6hr | T1/T2 | No key needed |
| Baltic Dry | via web scrape | Daily | T1/T2 | No key needed |
| LME warehouse | lme.com | Daily | T2 | Scrape or paid |

Start with EIA + GDELT + NOAA — all free, no key or free signup.

---

## Git Workflow

```bash
# Your branches live under oracle/
git checkout -b oracle/commodities-module
git checkout -b oracle/inventory-agent
git checkout -b oracle/geopolitical-agent

# PR into dev, never directly into main
```

---

## The Signal You're Reading

Remember the mental model at all times:

```
T3: Is the world structurally long or short this commodity? (years)
T2: Where are we in the current inventory / macro cycle? (months)
T1: Is the narrative accelerating or fading? (days)
T0: Is price confirming or diverging from the view? (now)

When T3 + T2 + T1 + T0 all align → highest conviction
When they split → the oracle says "insufficient signal — wait"
```

The oracle doesn't predict the heartbeat.
It tells you where in the breathing cycle the world is.
That's the edge.
