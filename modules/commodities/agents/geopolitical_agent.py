"""
Geopolitical Agent — T1/T2/T3
War is the world holding its breath.

Reads the war/conflict cycle phase:
  Escalation  → inhale  → bullish energy, bearish risk assets
  Stalemate   → held    → elevated vol, narrative-driven
  Resolution  → exhale  → supply routes reopen, risk premium compresses

Connects to: GDELT event database
Confidence range: 0.40–0.78

UPGRADE: Uses ONE Claude LLM call to reason about geopolitical context.
Falls back to threshold logic if LLM is unavailable.
"""

import json
import logging
from typing import Optional

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


logger = logging.getLogger(__name__)


# Escalation thresholds (GDELT tone-derived)
ESCALATION_HIGH = 0.6     # strong negative tone — active conflict
ESCALATION_MODERATE = 0.3  # elevated tension
ESCALATION_LOW = 0.15      # background noise

# LLM model for agent reasoning — fast, cheap, good enough
LLM_MODEL = "claude-sonnet-4-5"

GEOPOLITICAL_REASONING_PROMPT = """\
You are a geopolitical risk analyst interpreting GDELT event data for commodity market impact.

## Data
- Escalation score: {escalation_score:.3f} (0 = calm, 1 = acute conflict)
- Article count: {article_count} articles in last 7 days
- Active regions: {active_regions}
- Average tone: {avg_tone:.3f} (negative = conflict/tension, positive = cooperation)

## Your task
Assess the current war/conflict cycle phase and its impact on commodity prices over the next 1-4 weeks.

Classify the phase as one of:
1. **ESCALATION (inhale)**: Active conflict intensifying, new sanctions, military deployments, chokepoint threats. Bullish for commodities (supply risk premium rises).
2. **STALEMATE (held breath)**: Elevated tension but no new escalation or de-escalation. Narrative-driven volatility. Could go either way — lean neutral.
3. **RESOLUTION (exhale)**: Ceasefire talks, sanctions relief, diplomatic breakthroughs, supply routes reopening. Bearish for commodities (risk premium compresses).

Consider:
1. Is the escalation score high (>0.6), moderate (0.3-0.6), or low (<0.3)?
2. Which regions are active? Middle East/Hormuz and Red Sea directly affect oil supply routes. Ukraine/Russia affects gas and grain. Taiwan affects semiconductors.
3. Is the article volume unusually high (>40 articles = elevated attention) or low (<10 = calm)?
4. Is the tone strongly negative (<-3 = acute crisis) or mildly negative (-1 to -3 = background tension)?

## Rules
- Map cycle phase to direction: ESCALATION → BULLISH, STALEMATE → NEUTRAL, RESOLUTION → BEARISH.
- If the data is ambiguous or mixed signals, return NEUTRAL with lower confidence.
- Confidence must be between 0.40 and 0.78. Do NOT always return high confidence.
- If you truly cannot determine the phase, return UNKNOWN with confidence 0.30.
- Decay triggers must be SPECIFIC named events (e.g., "Iran-Saudi direct military confrontation"), never vague conditions like "situation changes".

## Response format
Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN",
  "confidence": <float between 0.40 and 0.78>,
  "cycle_phase": "escalation" | "stalemate" | "resolution" | "unknown",
  "price_impact": "upward" | "downward" | "neutral" | "uncertain",
  "reasoning": "<2-3 sentences explaining your assessment>",
  "decay_triggers": ["<specific event 1>", "<specific event 2>", "<specific event 3>"]
}}
"""


class GeopoliticalAgent:
    """
    Reads geopolitical event flow and maps it to the war/conflict cycle.
    Key regions: Middle East, Ukraine/Russia, Red Sea, Hormuz, Taiwan.

    Uses ONE Claude LLM call for contextual reasoning about the data.
    Falls back to threshold-based logic if the LLM is unavailable.
    """

    AGENT_ID = "geopolitical_agent"

    def __init__(self, gdelt_feed: GDELTFeed, client=None):
        self.feed = gdelt_feed
        self.client = client
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch geopolitical events and produce a directional signal.
        Escalation = bullish for commodities (supply risk).
        Resolution = bearish (risk premium drops).
        """
        result = self.feed.fetch(query="oil energy conflict sanctions war")

        # ── No data → honest UNKNOWN ────────────────────────────────
        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="GDELT feed unavailable — no geopolitical signal this cycle.",
            )

        data = result.data
        escalation = data.get("escalation_score", 0.0)
        article_count = data.get("article_count", 0)
        active_regions = data.get("active_regions", [])
        avg_tone = data.get("avg_tone", 0.0)

        # ── Try LLM reasoning, fall back to thresholds ──────────────
        llm_result = None
        if self.client is not None:
            llm_result = await self._reason_with_llm(
                escalation, article_count, active_regions, avg_tone
            )

        if llm_result is not None:
            direction, confidence, reasoning, layer, decay_triggers = llm_result
        else:
            # Fallback: threshold-based logic
            direction, confidence, reasoning, layer = self._interpret(
                escalation, article_count, active_regions
            )
            decay_triggers = [
                "Ceasefire agreement in key producing region",
                "New sanctions on major oil exporter",
                "Military escalation at key shipping chokepoint",
                "Diplomatic breakthrough (e.g. Iran nuclear deal)",
            ]

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT geopolitical events",
            value={
                "escalation_score": escalation,
                "article_count": article_count,
                "active_regions": active_regions,
            },
            direction=direction,
            confidence=confidence,
            layer=layer,
            domain_path=domain_path,
            decay_triggers=decay_triggers,
            reasoning=reasoning,
            raw_data=data,
        )

    async def _reason_with_llm(
        self,
        escalation: float,
        article_count: int,
        active_regions: list,
        avg_tone: float,
    ) -> Optional[tuple[SignalDirection, float, str, TemporalLayer, list[str]]]:
        """
        ONE LLM call to reason about the geopolitical data in context.
        Returns (direction, confidence, reasoning, layer, decay_triggers) or None on failure.
        """
        try:
            regions_str = ", ".join(active_regions) if active_regions else "none detected"

            prompt = GEOPOLITICAL_REASONING_PROMPT.format(
                escalation_score=escalation,
                article_count=article_count,
                active_regions=regions_str,
                avg_tone=avg_tone,
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
            direction_str = parsed.get("direction", "UNKNOWN").upper()
            direction_map = {
                "BULLISH": SignalDirection.BULLISH,
                "BEARISH": SignalDirection.BEARISH,
                "NEUTRAL": SignalDirection.NEUTRAL,
                "UNKNOWN": SignalDirection.UNKNOWN,
            }
            direction = direction_map.get(direction_str, SignalDirection.UNKNOWN)

            confidence = float(parsed.get("confidence", 0.50))
            # Clamp confidence to valid range
            confidence = max(0.40, min(0.78, confidence))

            reasoning = parsed.get("reasoning", "LLM provided no reasoning.")
            decay_triggers = parsed.get("decay_triggers", [])

            # Determine temporal layer from cycle phase
            cycle_phase = parsed.get("cycle_phase", "unknown")
            if cycle_phase == "escalation":
                layer = TemporalLayer.T1  # fast-moving, acute
            elif cycle_phase == "resolution":
                layer = TemporalLayer.T2  # unfolding over weeks
            else:
                layer = TemporalLayer.T1  # default for geopolitical

            # Validate decay triggers — must be specific
            if not decay_triggers or not isinstance(decay_triggers, list):
                decay_triggers = [
                    "Ceasefire agreement in key producing region",
                    "New sanctions on major oil exporter",
                    "Military escalation at key shipping chokepoint",
                ]

            return (direction, confidence, reasoning, layer, decay_triggers)

        except Exception as e:
            logger.warning(f"LLM reasoning failed, falling back to thresholds: {e}")
            return None

    def _interpret(
        self, escalation: float, article_count: int, active_regions: list
    ) -> tuple[SignalDirection, float, str, TemporalLayer]:
        """
        Map escalation score to direction and confidence.
        High escalation = bullish commodities (supply risk premium).
        """
        regions_str = ", ".join(active_regions) if active_regions else "none detected"

        if escalation >= ESCALATION_HIGH:
            return (
                SignalDirection.BULLISH,
                min(0.78, 0.60 + escalation * 0.2),
                f"High geopolitical escalation ({escalation:.2f}). "
                f"Active regions: {regions_str}. "
                f"Supply risk premium rising — bullish for commodities.",
                TemporalLayer.T1,
            )
        elif escalation >= ESCALATION_MODERATE:
            return (
                SignalDirection.BULLISH,
                0.55,
                f"Moderate geopolitical tension ({escalation:.2f}). "
                f"Active regions: {regions_str}. "
                f"Elevated but not acute — mild supply risk premium.",
                TemporalLayer.T1,
            )
        elif escalation >= ESCALATION_LOW:
            return (
                SignalDirection.NEUTRAL,
                0.45,
                f"Low-level geopolitical noise ({escalation:.2f}). "
                f"No acute supply chain threat detected.",
                TemporalLayer.T2,
            )
        else:
            return (
                SignalDirection.BEARISH,
                0.50,
                f"Geopolitical calm ({escalation:.2f}). "
                f"Risk premium likely compressing — mildly bearish for commodities.",
                TemporalLayer.T2,
            )
