"""
Inventory Agent — T2 (strategic, weeks → months)
The single most important commodity signal.

An inventory DRAW (stocks falling) = bullish for price.
An inventory BUILD (stocks rising) = bearish for price.

Connects to: EIA weekly petroleum data
Confidence range: 0.70–0.88 (hard data, high trust)

UPGRADE: Uses ONE Claude LLM call to reason about inventory context.
Falls back to threshold logic if LLM is unavailable.
"""

import json
import logging
from typing import Optional

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.eia import EIAFeed


logger = logging.getLogger(__name__)


# Thresholds for fallback logic (thousand barrels)
LARGE_DRAW_THRESHOLD = -3000    # draw > 3M bbl = strong bullish
SMALL_DRAW_THRESHOLD = -500     # draw > 500k bbl = mild bullish
SMALL_BUILD_THRESHOLD = 500     # build < 500k bbl = mild bearish
LARGE_BUILD_THRESHOLD = 3000    # build > 3M bbl = strong bearish

# LLM model for agent reasoning — fast, cheap, good enough
LLM_MODEL = "claude-sonnet-4-5"

INVENTORY_REASONING_PROMPT = """\
You are an oil market analyst interpreting US crude oil inventory data from the EIA Weekly Petroleum Status Report.

## Data
- Latest weekly stocks: {latest} thousand barrels
- Weekly change: {change:+,.0f} thousand barrels ({change_desc})
- 5-week trend (most recent first): {trend}
- Current month: {month}

## Your task
Determine whether this inventory data is BULLISH, BEARISH, or NEUTRAL for crude oil prices over the next 2-8 weeks.

Consider:
1. Is this week's draw/build large or small in context? (typical weekly change is ±1-4 million barrels)
2. Is the 5-week trend showing accumulation (bearish) or depletion (bullish)? Is it accelerating or decelerating?
3. Seasonality: US refineries typically draw heavily in summer driving season (May-Sep) and build in shoulder seasons (Oct-Nov, Feb-Mar). Is this build/draw expected for the season, or a surprise?
4. Absolute stock level: Are stocks historically high (>450M bbl, bearish) or low (<420M bbl, bullish)?

## Rules
- If the data is ambiguous or mixed signals, return NEUTRAL with lower confidence.
- Confidence must be between 0.50 and 0.88. Do NOT always return high confidence.
- If you truly cannot determine direction, return UNKNOWN with confidence 0.30.
- Decay triggers must be SPECIFIC named events (e.g., "OPEC announces output increase >500k bpd"), never vague conditions like "market changes".

## Response format
Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN",
  "confidence": <float between 0.50 and 0.88>,
  "reasoning": "<2-3 sentences explaining your interpretation>",
  "decay_triggers": ["<specific event 1>", "<specific event 2>", "<specific event 3>"]
}}
"""


class InventoryAgent:
    """
    Reads EIA weekly petroleum inventory data and produces a T2 signal.
    Hard data — this is the agent with the highest credibility weight.

    Uses ONE Claude LLM call for contextual reasoning about the data.
    Falls back to threshold-based logic if the LLM is unavailable.
    """

    AGENT_ID = "inventory_agent"

    def __init__(self, eia_feed: EIAFeed, client=None):
        self.feed = eia_feed
        self.client = client
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch latest inventory data and produce a directional signal.
        Returns UNKNOWN with low confidence if data is unavailable (ZERO FABRICATION).
        """
        result = self.feed.fetch()

        # ── No data → honest UNKNOWN ────────────────────────────────────
        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA weekly petroleum (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["EIA feed restored"],
                reasoning=f"EIA feed unavailable — no inventory data this cycle. Error: {result.error}",
            )

        data = result.data
        try:
            change = float(data["change"]) if data.get("change") is not None else None
            latest = float(data["latest"]) if data.get("latest") is not None else None
        except (TypeError, ValueError):
            change = None
            latest = None

        # ── No usable change data → UNKNOWN ─────────────────────────────
        if change is None:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="EIA weekly petroleum",
                value=data,
                direction=SignalDirection.UNKNOWN,
                confidence=0.30,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["Next EIA weekly release"],
                reasoning="EIA data received but change could not be calculated.",
            )

        # ── Try LLM reasoning, fall back to thresholds ──────────────────
        llm_result = None
        if self.client is not None:
            llm_result = await self._reason_with_llm(data, change, latest)

        if llm_result is not None:
            direction, confidence, reasoning, decay_triggers = llm_result
        else:
            # Fallback: threshold-based logic
            direction, confidence, reasoning = self._interpret(change, latest)
            decay_triggers = [
                "OPEC announces output increase >500k bpd",
                "US SPR release >20M barrels announced",
                "Major demand shock (e.g. China lockdown)",
                "EIA revises prior week data significantly",
            ]

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="EIA weekly petroleum",
            value={
                "latest_stocks": latest,
                "weekly_change": change,
                "unit": data.get("unit", "thousand barrels"),
            },
            direction=direction,
            confidence=confidence,
            layer=TemporalLayer.T2,
            domain_path=domain_path,
            decay_triggers=decay_triggers,
            reasoning=reasoning,
            raw_data=data,
        )

    async def _reason_with_llm(
        self, data: dict, change: float, latest: Optional[float]
    ) -> Optional[tuple[SignalDirection, float, str, list[str]]]:
        """
        ONE LLM call to reason about the inventory data in context.
        Returns (direction, confidence, reasoning, decay_triggers) or None on failure.
        """
        try:
            # Build trend from readings
            readings = data.get("readings", [])
            trend_values = []
            for i in range(min(6, len(readings)) - 1):
                curr = readings[i].get("value")
                prev = readings[i + 1].get("value")
                if curr is not None and prev is not None:
                    try:
                        trend_values.append(float(curr) - float(prev))
                    except (TypeError, ValueError):
                        pass

            trend_str = ", ".join(f"{v:+,.0f}" for v in trend_values) if trend_values else "insufficient data"
            change_desc = "draw" if change < 0 else "build" if change > 0 else "flat"

            from datetime import datetime, timezone
            current_month = datetime.now(timezone.utc).strftime("%B %Y")

            latest_str = f"{latest:,.0f}" if latest is not None else "unknown"

            prompt = INVENTORY_REASONING_PROMPT.format(
                latest=latest_str,
                change=change,
                change_desc=change_desc,
                trend=trend_str,
                month=current_month,
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
            confidence = max(0.30, min(0.88, confidence))

            reasoning = parsed.get("reasoning", "LLM provided no reasoning.")
            decay_triggers = parsed.get("decay_triggers", [])

            # Validate decay triggers — must be specific
            if not decay_triggers or not isinstance(decay_triggers, list):
                decay_triggers = [
                    "Next EIA weekly petroleum release",
                    "OPEC announces output change",
                    "US SPR policy announcement",
                ]

            return (direction, confidence, reasoning, decay_triggers)

        except Exception as e:
            logger.warning(f"LLM reasoning failed, falling back to thresholds: {e}")
            return None

    def _interpret(self, change: float, latest) -> tuple[SignalDirection, float, str]:
        """
        Fallback: Convert raw inventory change into direction + confidence.
        Larger moves = higher confidence.
        """
        latest_str = f"{latest:,.0f}k bbl" if latest else "unknown level"

        if change <= LARGE_DRAW_THRESHOLD:
            return (
                SignalDirection.BULLISH,
                0.85,
                f"Large inventory draw of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Strong supply tightening signal.",
            )
        elif change <= SMALL_DRAW_THRESHOLD:
            return (
                SignalDirection.BULLISH,
                0.72,
                f"Moderate inventory draw of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Supply modestly tightening.",
            )
        elif change < SMALL_BUILD_THRESHOLD:
            return (
                SignalDirection.NEUTRAL,
                0.60,
                f"Inventory roughly flat ({change:+,.0f}k bbl). "
                f"Stocks at {latest_str}. No clear supply signal.",
            )
        elif change < LARGE_BUILD_THRESHOLD:
            return (
                SignalDirection.BEARISH,
                0.72,
                f"Moderate inventory build of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Supply loosening.",
            )
        else:
            return (
                SignalDirection.BEARISH,
                0.85,
                f"Large inventory build of {change:+,.0f}k bbl. "
                f"Stocks at {latest_str}. Strong supply glut signal.",
            )
