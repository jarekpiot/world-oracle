"""
World Oracle — Layer 1: Query Understanding
The orchestrator LLM parses every incoming query regardless of asset class.
Produces a DecomposedQuery with domain path, temporal layer, and DAG of sub-tasks.
"""

import json
import os
from datetime import datetime, timezone

import anthropic

from core.registry import DecomposedQuery, QueryType, TemporalLayer


SYSTEM_PROMPT = """You are the query understanding layer of the World Oracle system.

The World Oracle reads the world the way a doctor reads a patient's breathing —
not just the price (heartbeat) but the deep rhythms underneath:
trade flows, geopolitics, weather, supply cycles, narrative momentum.

Your job: decompose any incoming query into a structured plan.

TEMPORAL LAYERS — every query belongs to one:
  T0 = realtime    (seconds–minutes)  the heartbeat
  T1 = tactical    (hours–days)       quick breath
  T2 = strategic   (weeks–months)     regular breath — THIS IS THE SWEET SPOT
  T3 = structural  (months–years)     slow breath

DOMAIN PATHS — use this format:
  commodity.energy.crude_oil
  commodity.energy.natural_gas
  commodity.metals.copper
  commodity.metals.gold
  commodity.agriculture.wheat
  commodity.agriculture.corn
  fx.major.eurusd
  fx.major.usdjpy
  fx.em.usdtry
  crypto.l1.bitcoin
  crypto.l1.solana
  equity.index.sp500
  macro.rates.us_10y
  macro.inflation.cpi_us
  geo.conflict.middle_east
  geo.policy.opec

QUERY TYPES:
  factual     = what is the current state?
  predictive  = where is this going?
  causal      = why is this happening?
  comparative = which is stronger / weaker?

Return ONLY valid JSON — no preamble, no markdown:
{
  "query_type": "predictive",
  "domain_path": "commodity.energy.crude_oil",
  "temporal_layer": "T2",
  "confidence_threshold": 0.65,
  "sub_tasks": [
    {"id": "supply_signal",   "depends_on": [],                        "agent_hint": "inventory"},
    {"id": "demand_signal",   "depends_on": [],                        "agent_hint": "macro_demand"},
    {"id": "geo_signal",      "depends_on": [],                        "agent_hint": "geopolitical"},
    {"id": "narrative_signal","depends_on": [],                        "agent_hint": "narrative"},
    {"id": "synthesis",       "depends_on": ["supply_signal","demand_signal","geo_signal","narrative_signal"]}
  ],
  "reasoning": "brief explanation of decomposition choices"
}

CONFIDENCE THRESHOLD GUIDE:
  0.80+ = only return answer if very high confidence (institutional use)
  0.65  = standard threshold (default for most queries)
  0.50  = acceptable for exploratory / research queries
  0.40  = low bar — always return something (not recommended for trading)

IMPORTANT: sub_tasks with no depends_on run in PARALLEL. 
Only add depends_on when a task genuinely needs prior results.
Synthesis always depends on all signal tasks."""


class QueryEngine:
    """
    Layer 1 — Query Understanding.
    Takes raw natural language, returns a structured DecomposedQuery.
    This is the universal entry point — asset-agnostic.
    """

    def __init__(self, client: anthropic.AsyncAnthropic):
        self.client = client

    async def decompose(self, raw_query: str) -> DecomposedQuery:
        """
        Decompose a raw query into a structured plan.
        The domain path produced here routes everything that follows.
        """
        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": raw_query}]
        )

        raw_text = response.content[0].text.strip()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Fallback — extract JSON if wrapped in any prose
            import re
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Layer 1 could not parse response: {raw_text[:200]}")

        layer_map = {"T0": TemporalLayer.T0, "T1": TemporalLayer.T1,
                     "T2": TemporalLayer.T2, "T3": TemporalLayer.T3}

        return DecomposedQuery(
            raw=raw_query,
            query_type=QueryType(data["query_type"]),
            domain_path=data["domain_path"],
            temporal_layer=layer_map[data["temporal_layer"]],
            confidence_threshold=float(data["confidence_threshold"]),
            sub_tasks=data["sub_tasks"],
            reasoning=data.get("reasoning", ""),
        )

    def build_dag(self, sub_tasks: list[dict]) -> dict:
        """
        Build an execution DAG from sub_tasks.
        Returns {task_id: [dependency_ids]} and execution order.
        Tasks with no dependencies can run in parallel (wave 0).
        """
        dag = {t["id"]: t.get("depends_on", []) for t in sub_tasks}
        waves = []
        resolved = set()

        remaining = set(dag.keys())
        while remaining:
            wave = {t for t in remaining if all(d in resolved for d in dag[t])}
            if not wave:
                # Cycle detection
                raise ValueError(f"DAG cycle detected in sub_tasks: {remaining}")
            waves.append(sorted(wave))
            resolved |= wave
            remaining -= wave

        return {"dag": dag, "execution_waves": waves}

    def log_decomposition(self, query: DecomposedQuery) -> None:
        """Print a clean summary of how a query was decomposed."""
        print(f"\n[L1] ─── Query Decomposition ───────────────────────")
        print(f"[L1] Raw:       {query.raw[:80]}")
        print(f"[L1] Type:      {query.query_type.value}")
        print(f"[L1] Domain:    {query.domain_path}")
        print(f"[L1] Temporal:  {query.temporal_layer.value}")
        print(f"[L1] Threshold: {query.confidence_threshold}")
        print(f"[L1] Tasks:     {[t['id'] for t in query.sub_tasks]}")
        if query.reasoning:
            print(f"[L1] Reasoning: {query.reasoning[:120]}")
        print(f"[L1] ────────────────────────────────────────────────\n")
