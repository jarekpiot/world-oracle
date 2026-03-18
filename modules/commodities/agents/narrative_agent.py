"""
Narrative Agent — T0/T1
How is the story moving? Narratives drive short-term price action.

This agent reads the momentum of the current narrative:
  Accelerating bullish narrative → T1 bullish (momentum)
  Fading narrative → signal weakening
  Narrative reversal → counter-trend risk

Connects to: GDELT (news tone), future: social sentiment
Confidence range: 0.35–0.65 (lowest raw credibility — narratives are noisy)

UPGRADE: Uses ONE Claude LLM call to reason about narrative momentum.
Falls back to threshold logic if LLM is unavailable.
"""

import json
import logging
from typing import Optional

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.gdelt import GDELTFeed


logger = logging.getLogger(__name__)


# LLM model for agent reasoning — fast, cheap, good enough
LLM_MODEL = "claude-sonnet-4-5"

NARRATIVE_REASONING_PROMPT = """\
You are a commodity market narrative analyst interpreting news momentum data from GDELT.

## Data
- Domain: {domain_path}
- Search query used: "{query}"
- Article count (recent window): {article_count}
- Average tone score: {avg_tone:.2f} (negative = fear/concern, positive = optimism; typical range -5 to +5)

## Your task
Assess the narrative momentum for this commodity market. Determine whether the current news narrative is BULLISH, BEARISH, or NEUTRAL for prices over the next few days to 2 weeks.

Consider:
1. Is the narrative accelerating (growing volume + strengthening tone) or fading (declining volume)?
2. Is fear or greed the dominant emotion? Fear narratives around supply disruption are typically bullish for commodities. Complacency/optimism narratives can signal bearish reversals.
3. High article volume with strongly negative tone = crisis/fear narrative (usually bullish for commodities via supply disruption concerns).
4. High article volume with positive tone = optimism/complacency (watch for bearish reversal).
5. Low article volume = narrative is fading, no strong momentum signal.
6. Narratives are NOISY — keep confidence low. Do not overstate certainty.

## Rules
- If the data is ambiguous or mixed signals, return NEUTRAL with lower confidence.
- Confidence must be between 0.35 and 0.65. Narratives are noisy — NEVER return high confidence.
- If you truly cannot determine direction, return UNKNOWN with confidence 0.30.
- Decay triggers must be SPECIFIC named events (e.g., "Tone shifts >2 points in 24h"), never vague conditions like "market changes".

## Response format
Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN",
  "confidence": <float between 0.35 and 0.65>,
  "reasoning": "<2-3 sentences explaining your interpretation of the narrative momentum>",
  "decay_triggers": ["<specific event 1>", "<specific event 2>", "<specific event 3>"]
}}
"""


class NarrativeAgent:
    """
    Reads news narrative momentum for commodity markets.
    Uses GDELT article volume and tone as a proxy for narrative velocity.
    Lowest credibility weight — useful but noisy.

    Uses ONE Claude LLM call for contextual reasoning about the narrative.
    Falls back to threshold-based logic if the LLM is unavailable.
    """

    AGENT_ID = "narrative_agent"

    def __init__(self, gdelt_feed: GDELTFeed, client=None):
        self.feed = gdelt_feed
        self.client = client
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Measure narrative momentum via news volume and tone.
        """
        # Build a commodity-specific query from the domain path
        query = self._domain_to_query(domain_path)
        result = self.feed.fetch(query=query)

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="GDELT narrative (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["GDELT feed restored"],
                reasoning="News narrative feed unavailable — no sentiment signal this cycle.",
            )

        data = result.data
        article_count = data.get("article_count", 0)
        avg_tone = data.get("avg_tone", 0.0)

        # ── Try LLM reasoning, fall back to thresholds ──────────────────
        llm_result = None
        if self.client is not None:
            llm_result = await self._reason_with_llm(
                article_count, avg_tone, domain_path, query
            )

        if llm_result is not None:
            direction, confidence, reasoning, decay_triggers = llm_result
        else:
            # Fallback: threshold-based logic
            direction, confidence, reasoning = self._interpret(article_count, avg_tone, domain_path)
            decay_triggers = [
                "Narrative reversal — tone shifts >2 points in 24h",
                "Major counter-narrative event (e.g. surprise data release)",
                "News volume drops below 10 articles/day on topic",
            ]

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="GDELT news narrative",
            value={
                "article_count": article_count,
                "avg_tone": avg_tone,
                "query": query,
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T1,
            domain_path=domain_path,
            decay_triggers=decay_triggers,
            reasoning=reasoning,
            raw_data=data,
        )

    async def _reason_with_llm(
        self, article_count: int, avg_tone: float, domain_path: str, query: str
    ) -> Optional[tuple[SignalDirection, float, str, list[str]]]:
        """
        ONE LLM call to reason about narrative momentum in context.
        Returns (direction, confidence, reasoning, decay_triggers) or None on failure.
        """
        try:
            prompt = NARRATIVE_REASONING_PROMPT.format(
                domain_path=domain_path,
                query=query,
                article_count=article_count,
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

            confidence = float(parsed.get("confidence", 0.45))
            # Clamp confidence to valid range for narratives (noisy signal)
            confidence = max(0.30, min(0.65, confidence))

            reasoning = parsed.get("reasoning", "LLM provided no reasoning.")
            decay_triggers = parsed.get("decay_triggers", [])

            # Validate decay triggers — must be specific
            if not decay_triggers or not isinstance(decay_triggers, list):
                decay_triggers = [
                    "Narrative reversal — tone shifts >2 points in 24h",
                    "Major counter-narrative event (e.g. surprise data release)",
                    "News volume drops below 10 articles/day on topic",
                ]

            return (direction, confidence, reasoning, decay_triggers)

        except Exception as e:
            logger.warning(f"LLM reasoning failed, falling back to thresholds: {e}")
            return None

    def _domain_to_query(self, domain_path: str) -> str:
        """Map domain path to a GDELT search query."""
        parts = domain_path.split(".")
        query_map = {
            "crude_oil":    "crude oil price supply demand OPEC",
            "natural_gas":  "natural gas LNG price supply",
            "gold":         "gold price safe haven demand",
            "copper":       "copper price industrial demand China",
            "wheat":        "wheat price crop harvest supply",
            "corn":         "corn price ethanol crop",
        }
        asset = parts[-1] if len(parts) > 1 else "commodity"
        return query_map.get(asset, f"{asset} commodity price supply demand")

    def _interpret(
        self, article_count: int, avg_tone: float, domain_path: str
    ) -> tuple[SignalDirection, float, str]:
        """
        Interpret narrative signals.
        High volume + negative tone = fear narrative (bullish for safe havens, mixed for energy).
        High volume + positive tone = optimism narrative.
        Low volume = narrative fading.
        """
        if article_count < 5:
            return (
                SignalDirection.NEUTRAL,
                0.35,
                f"Low news volume ({article_count} articles) — narrative is quiet. "
                f"No strong momentum in either direction.",
            )

        # Negative tone with high volume = crisis/fear narrative
        if avg_tone < -2.0 and article_count > 20:
            return (
                SignalDirection.BULLISH,
                0.60,
                f"Strong negative narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Fear/crisis narrative accelerating — typically bullish for commodities "
                f"via supply disruption concerns.",
            )

        if avg_tone < -1.0:
            return (
                SignalDirection.BULLISH,
                0.50,
                f"Moderately negative narrative (tone {avg_tone:.1f}). "
                f"Concern narrative building but not dominant.",
            )

        if avg_tone > 1.0 and article_count > 20:
            return (
                SignalDirection.BEARISH,
                0.50,
                f"Positive narrative ({article_count} articles, tone {avg_tone:.1f}). "
                f"Optimism may indicate complacency — watch for reversal.",
            )

        return (
            SignalDirection.NEUTRAL,
            0.40,
            f"Narrative is balanced (tone {avg_tone:.1f}, {article_count} articles). "
            f"No clear directional momentum from news flow.",
        )
