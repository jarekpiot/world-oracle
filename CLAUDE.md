# Project Breathe — CLAUDE.md
## Auto-loaded every session by Claude Code

---

## Step 1 — Always read SPEC.md first

Before doing anything else, read SPEC.md in full.
It contains the full project context, architecture, absolute rules,
and the temporal model. Do not skip this step.

---

## Step 2 — Identify your team from the task

Read the task you have been given and assign yourself to the
correct team using this decision table:

| If the task involves...                          | You are...          | Also read...          |
|--------------------------------------------------|---------------------|-----------------------|
| core/, api/, db/, tests/, CI/CD, Railway, Docker | BUILD TEAM          | BUILD_TEAM.md         |
| modules/, agents/, feeds/, signal logic          | ORACLE TEAM         | ORACLE_TEAM.md        |
| dashboard/visual/, 3D globe, breathing animation | VISUAL ENGINEER     | VISUAL_ENGINEER.md    |
| You are unsure                                   | Ask before starting | Read all three        |

---

## Step 3 — Confirm your boundaries before touching any file

### If you are BUILD TEAM
You may modify:
  core/  api/  db/  output/  tests/  .github/  main.py  requirements.txt
You may NOT modify:
  modules/  ORACLE_TEAM.md  VISUAL_ENGINEER.md

### If you are ORACLE TEAM
You may modify:
  modules/  (and only modules/)
You may NOT modify:
  core/  api/  db/  dashboard/  tests/  .github/

### If you are VISUAL ENGINEER
You may modify:
  dashboard/visual/  (and only dashboard/visual/)
You may NOT modify:
  core/  modules/  api/  db/  tests/

---

## Step 4 — The absolute rules (apply to all teams, always)

1. ZERO FABRICATION — unknown data = UNKNOWN direction, never a guess
2. Oracle ABSTAINS when confidence < threshold — INSUFFICIENT_SIGNAL is valid
3. One LLM call per synthesis — no chained reasoning within one agent
4. Every signal must have: confidence + temporal_layer + decay_triggers + reasoning
5. Tests must pass before any commit — all 177 must stay green
6. core/registry.py module contract does not change without both teams agreeing
7. Decay triggers must be SPECIFIC named events, not vague conditions
8. T0 signals do not override T2 views — different horizons, different questions
9. PostgreSQL only in production — SQLite causes data loss on Railway deploy
10. All database operations must be async — never block the event loop

---

## Step 5 — Run tests before pushing

```bash
DATABASE_URL=sqlite+aiosqlite:///test.db python -m pytest tests/ -v
```

All 167 tests must pass. If any fail — fix before pushing.
Never push a failing test to main.

---

## Project at a glance

```
Live API:   https://world-oracle-production.up.railway.app
Visual:     https://world-oracle-production.up.railway.app/visual/
Repo:       https://github.com/jarekpiot/world-oracle
CI/CD:      GitHub Actions → Railway auto-deploy on main push
Database:   PostgreSQL on Railway (persistent across deploys)
Tests:      177 passing across 11 test files
```

## Current known issues (fix these first)
- GDELT returning 429 Too Many Requests → needs caching + backoff
- Baltic Dry → no free feed, needs paid provider
- Crypto onchain → needs Glassnode/Dune integration

## Stack
```
Python 3.11 · FastAPI · SQLAlchemy async · asyncpg · PostgreSQL
Railway · GitHub Actions · Alembic · pytest
Canvas 2D + Three.js r149 · GSAP 3
```

## Team files
- SPEC.md              ← full project specification (READ FIRST)
- BUILD_TEAM.md        ← platform team directives
- ORACLE_TEAM.md       ← intelligence team directives
- VISUAL_ENGINEER.md   ← visual spec and standards
- state.md             ← current build status (update after each session)
