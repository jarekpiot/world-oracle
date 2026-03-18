"""
Structural Agent — T3 (months → years)
The slow breath — where is the world structurally?

This agent reads secular trends:
  Energy transition     → coal declining, gas bridging, renewables rising
  Commodity supercycle  → 20-30 year demand waves (are we early or late?)
  Dollar cycle          → strong USD = headwind for commodities
  Demographic shift     → urbanisation, ageing populations
  De-globalisation      → supply chain reshoring, higher baseline costs

This is the LEAST frequently updated agent (monthly cadence).
It sets the structural backdrop — the deep current beneath the waves.

Confidence range: 0.40–0.72

UPGRADE: Uses ONE Claude LLM call to reason about structural outlook.
Falls back to curated views if LLM is unavailable.
"""

import json
import logging
from typing import Optional

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine


logger = logging.getLogger(__name__)


# LLM model for agent reasoning — fast, cheap, good enough
LLM_MODEL = "claude-sonnet-4-5"

STRUCTURAL_REASONING_PROMPT = """\
You are a macro strategist assessing the T3 structural outlook for a commodity over the next 12-36 months.
This is the SLOW BREATH — the deep current beneath the waves, updated on a monthly cadence.

## Domain
- Commodity path: {domain_path}

## Current curated structural view (as context)
- Direction: {curated_direction}
- Confidence: {curated_confidence}
- Thesis: {curated_thesis}
- Horizon: {curated_horizon}

## Your task
Assess the T3 structural outlook for this commodity. Consider all five structural forces:

1. **Energy transition**: How does the shift from fossil fuels to renewables affect long-term demand for this commodity? Is demand structurally rising, declining, or stable?
2. **Supercycles**: Where are we in the 20-30 year commodity supercycle? Are we in the early investment phase (bullish), the peak (neutral), or the late/declining phase (bearish)?
3. **Dollar cycle**: Is the USD structurally strengthening (headwind for commodities) or weakening (tailwind)? Consider Fed policy trajectory, fiscal deficits, and de-dollarisation trends.
4. **Demographic shifts**: How do global demographic trends (urbanisation in developing world, ageing in developed world, population growth) affect structural demand?
5. **Supply discipline**: Are producers investing in new supply (bearish long-term) or under-investing (bullish long-term)? Consider capex trends, ESG constraints on investment, and resource depletion.

## Rules
- This is a STRUCTURAL view — ignore short-term noise. Think in terms of years, not weeks.
- Confidence must be between 0.40 and 0.72. Structural views are inherently uncertain.
- If structural forces are mixed or offsetting, return NEUTRAL with lower confidence.
- Decay triggers must be SPECIFIC structural shifts (e.g., "Major economy announces ban on ICE vehicles by 2030"), never vague conditions.

## Response format
Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN",
  "confidence": <float between 0.40 and 0.72>,
  "reasoning": "<2-3 sentences explaining the structural assessment>",
  "decay_triggers": ["<specific structural shift 1>", "<specific structural shift 2>", "<specific structural shift 3>"]
}}
"""


# Structural views — updated infrequently based on macro regime shifts.
# These are starting positions, not predictions.
# The agent's job is to hold the structural context that shorter-term
# agents can lean on or push against.
STRUCTURAL_VIEWS = {
    "commodity.energy.crude_oil": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.55,
        "thesis": "Energy transition creates long-term demand uncertainty for crude. "
                  "Near-term (2-5y) demand remains resilient due to developing world growth. "
                  "Supply discipline from OPEC+ supports prices but shale flexibility caps upside.",
        "horizon": "12-36 months",
    },
    "commodity.energy.natural_gas": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.60,
        "thesis": "Natural gas is the transition fuel. LNG demand structurally rising as "
                  "Europe diversifies from Russian supply and Asia coal-to-gas switching continues.",
        "horizon": "12-36 months",
    },
    "commodity.metals.copper": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.65,
        "thesis": "Electrification and energy transition are copper-intensive. "
                  "EV, grid, renewables all require more copper. Supply pipeline is thin.",
        "horizon": "18-36 months",
    },
    "commodity.metals.gold": {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.58,
        "thesis": "Central bank buying (de-dollarisation), geopolitical uncertainty, "
                  "and eventual rate cutting cycle support structural gold demand.",
        "horizon": "12-24 months",
    },
    "commodity.agriculture.wheat": {
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.45,
        "thesis": "Climate change increases yield volatility but technology improves productivity. "
                  "Black Sea supply remains uncertain due to conflict.",
        "horizon": "12-24 months",
    },
}

# Default for domains not explicitly mapped
DEFAULT_STRUCTURAL = {
    "direction": SignalDirection.NEUTRAL,
    "confidence": 0.40,
    "thesis": "No strong structural view for this commodity. "
              "Structural analysis requires domain-specific research.",
    "horizon": "12-36 months",
}


class StructuralAgent:
    """
    Provides the T3 structural backdrop — the slow breath.
    Updated infrequently (monthly). Sets the deep current direction.
    Other agents' signals are more actionable but this provides context.

    Uses ONE Claude LLM call for contextual reasoning about structural outlook.
    Falls back to curated STRUCTURAL_VIEWS if the LLM is unavailable.
    """

    AGENT_ID = "structural_agent"

    def __init__(self, client=None):
        self.client = client
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Return the structural view for the given domain.
        Tries LLM reasoning first, falls back to curated structural views.
        """
        view = STRUCTURAL_VIEWS.get(domain_path, DEFAULT_STRUCTURAL)

        # ── Try LLM reasoning, fall back to curated views ────────────
        llm_result = None
        if self.client is not None:
            llm_result = await self._reason_with_llm(domain_path, view)

        if llm_result is not None:
            direction, confidence, reasoning, decay_triggers = llm_result
        else:
            # Fallback: curated structural views
            direction = view["direction"]
            confidence = view["confidence"]
            reasoning = view["thesis"]
            decay_triggers = [
                "Major policy shift (e.g. new energy legislation)",
                "Structural demand destruction event",
                "Technology breakthrough altering supply/demand balance",
                "Monthly structural review by Oracle Team",
            ]

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="Oracle Team structural assessment",
            value={
                "thesis": reasoning,
                "horizon": view["horizon"],
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T3,
            domain_path=domain_path,
            decay_triggers=decay_triggers,
            reasoning=reasoning,
            valid_horizon=view["horizon"],
        )

    async def _reason_with_llm(
        self, domain_path: str, view: dict
    ) -> Optional[tuple[SignalDirection, float, str, list[str]]]:
        """
        ONE LLM call to reason about the structural outlook in context.
        Returns (direction, confidence, reasoning, decay_triggers) or None on failure.
        """
        try:
            # Map direction enum to string for the prompt
            direction_str = view["direction"].value.upper()

            prompt = STRUCTURAL_REASONING_PROMPT.format(
                domain_path=domain_path,
                curated_direction=direction_str,
                curated_confidence=view["confidence"],
                curated_thesis=view["thesis"],
                curated_horizon=view["horizon"],
            )

            response = await self.client.messages.create(
                model=LLM_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            content = response.content[0].text.strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            parsed = json.loads(content)

            # Validate and extract
            direction_raw = parsed.get("direction", "UNKNOWN").upper()
            direction_map = {
                "BULLISH": SignalDirection.BULLISH,
                "BEARISH": SignalDirection.BEARISH,
                "NEUTRAL": SignalDirection.NEUTRAL,
                "UNKNOWN": SignalDirection.UNKNOWN,
            }
            direction = direction_map.get(direction_raw, SignalDirection.UNKNOWN)

            confidence = float(parsed.get("confidence", 0.50))
            # Clamp confidence to valid range for T3: 0.40–0.72
            confidence = max(0.40, min(0.72, confidence))

            reasoning = parsed.get("reasoning", "LLM provided no reasoning.")
            decay_triggers = parsed.get("decay_triggers", [])

            # Validate decay triggers — must be specific
            if not decay_triggers or not isinstance(decay_triggers, list):
                decay_triggers = [
                    "Major policy shift (e.g. new energy legislation)",
                    "Structural demand destruction event",
                    "Technology breakthrough altering supply/demand balance",
                ]

            return (direction, confidence, reasoning, decay_triggers)

        except Exception as e:
            logger.warning(f"LLM reasoning failed, falling back to curated views: {e}")
            return None
