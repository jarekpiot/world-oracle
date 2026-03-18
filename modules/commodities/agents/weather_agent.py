"""
Weather Agent — T1/T2
Weather is nature's breath — hurricanes, droughts, cold snaps all move commodities.

  Hurricane in Gulf → oil production shutdowns → bullish energy
  Drought in Midwest → crop stress → bullish agriculture
  Cold snap → nat gas demand spike → bullish energy

Connects to: NOAA weather alerts
Confidence range: 0.40–0.80

UPGRADE: Uses ONE Claude LLM call to reason about weather impact on commodities.
Falls back to threshold logic if LLM is unavailable.
"""

import json
import logging
from typing import Optional

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.noaa import NOAAFeed


logger = logging.getLogger(__name__)


# LLM model for agent reasoning — fast, cheap, good enough
LLM_MODEL = "claude-sonnet-4-5"

WEATHER_REASONING_PROMPT = """\
You are a commodity supply-chain analyst assessing NOAA weather data for potential supply disruptions.

## Data
- Total active weather alerts: {alert_count}
- Severe/extreme alerts: {severe_count}
- Hurricane active: {hurricane_active}
- Drought active: {drought_active}
- Cold snap active: {cold_snap_active}
- Commodity domain: {domain_path}

## Your task
Determine whether these weather conditions will disrupt commodity supply chains. Return BULLISH (supply disruption = price up), BEARISH (favorable weather = price pressure down), or NEUTRAL.

Consider:
1. Domain relevance: energy domains (oil, gas) are most affected by hurricanes (Gulf production shutdowns) and cold snaps (heating demand spikes). Agriculture domains are most affected by drought and extreme heat (crop stress, yield reduction).
2. Severity: A single hurricane in the Gulf can shut down 10-20% of US oil production. A major drought can cut crop yields by 20-40%. Cold snaps spike natural gas demand 30-50% above normal.
3. Alert volume: Many severe alerts suggest widespread disruption. Few or no alerts suggest normal conditions.
4. Cross-domain effects: Hurricanes also disrupt shipping and refining. Drought affects river transport (barge traffic). Cold snaps can freeze pipelines.

## Rules
- If no significant weather events are active, return NEUTRAL with confidence around 0.50.
- Confidence must be between 0.40 and 0.80. Do NOT always return high confidence.
- If you truly cannot determine impact, return UNKNOWN with confidence 0.30.
- Decay triggers must be SPECIFIC weather events (e.g., "Hurricane makes landfall and dissipates"), never vague conditions.

## Response format
Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN",
  "confidence": <float between 0.40 and 0.80>,
  "reasoning": "<2-3 sentences explaining the weather impact assessment>",
  "decay_triggers": ["<specific event 1>", "<specific event 2>", "<specific event 3>"],
  "layer": "T1" | "T2"
}}
"""


class WeatherAgent:
    """
    Reads NOAA weather alerts and maps supply-disrupting weather to commodity signals.

    Uses ONE Claude LLM call for contextual reasoning about weather impact.
    Falls back to threshold-based logic if the LLM is unavailable.
    """

    AGENT_ID = "weather_agent"

    def __init__(self, noaa_feed: NOAAFeed, client=None):
        self.feed = noaa_feed
        self.client = client
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch weather alerts and produce a directional signal.
        Severe weather in commodity-producing regions = bullish (supply disruption).
        """
        result = self.feed.fetch()

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="NOAA (unavailable)",
                value={"error": result.error},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T1,
                domain_path=domain_path,
                decay_triggers=["NOAA feed restored"],
                reasoning="NOAA feed unavailable — no weather signal this cycle.",
            )

        data = result.data

        # ── Try LLM reasoning, fall back to thresholds ──────────────────
        llm_result = None
        if self.client is not None:
            llm_result = await self._reason_with_llm(data, domain_path)

        if llm_result is not None:
            direction, confidence, reasoning, decay_triggers, layer = llm_result
        else:
            # Fallback: threshold-based logic
            direction, confidence, reasoning, layer = self._interpret(data, domain_path)
            decay_triggers = [
                "Hurricane/storm system dissipates",
                "Drought conditions ease with rainfall",
                "Temperature normalisation forecast",
                "NOAA downgrades severity of active alerts",
            ]

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="NOAA weather alerts",
            value={
                "alert_count": data.get("alert_count", 0),
                "severe_count": data.get("severe_count", 0),
                "hurricane_active": data.get("hurricane_active", False),
                "drought_active": data.get("drought_active", False),
                "cold_snap_active": data.get("cold_snap_active", False),
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
        self, data: dict, domain_path: str
    ) -> Optional[tuple[SignalDirection, float, str, list[str], TemporalLayer]]:
        """
        ONE LLM call to reason about weather impact on commodity supply chains.
        Returns (direction, confidence, reasoning, decay_triggers, layer) or None on failure.
        """
        try:
            prompt = WEATHER_REASONING_PROMPT.format(
                alert_count=data.get("alert_count", 0),
                severe_count=data.get("severe_count", 0),
                hurricane_active=data.get("hurricane_active", False),
                drought_active=data.get("drought_active", False),
                cold_snap_active=data.get("cold_snap_active", False),
                domain_path=domain_path,
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
            confidence = max(0.30, min(0.80, confidence))

            reasoning = parsed.get("reasoning", "LLM provided no reasoning.")
            decay_triggers = parsed.get("decay_triggers", [])

            # Validate decay triggers — must be specific
            if not decay_triggers or not isinstance(decay_triggers, list):
                decay_triggers = [
                    "Hurricane/storm system dissipates",
                    "Drought conditions ease with rainfall",
                    "Temperature normalisation forecast",
                ]

            # Parse temporal layer
            layer_str = parsed.get("layer", "T1").upper()
            layer_map = {"T1": TemporalLayer.T1, "T2": TemporalLayer.T2}
            layer = layer_map.get(layer_str, TemporalLayer.T1)

            return (direction, confidence, reasoning, decay_triggers, layer)

        except Exception as e:
            logger.warning(f"LLM reasoning failed, falling back to thresholds: {e}")
            return None

    def _interpret(
        self, data: dict, domain_path: str
    ) -> tuple[SignalDirection, float, str, TemporalLayer]:
        """
        Map weather conditions to commodity price direction.
        Domain-aware: energy domains care about hurricanes/cold,
        agriculture domains care about drought/heat.
        """
        hurricane = data.get("hurricane_active", False)
        drought = data.get("drought_active", False)
        cold_snap = data.get("cold_snap_active", False)
        severe_count = data.get("severe_count", 0)
        is_energy = "energy" in domain_path
        is_agriculture = "agriculture" in domain_path

        # Hurricane — major for energy (Gulf production shutdowns)
        if hurricane and is_energy:
            return (
                SignalDirection.BULLISH,
                0.80,
                "Active hurricane in Gulf region — oil/gas production shutdowns likely. "
                "Historically causes 5-15% supply disruption during storm season.",
                TemporalLayer.T1,
            )

        # Drought — major for agriculture
        if drought and is_agriculture:
            return (
                SignalDirection.BULLISH,
                0.75,
                "Active drought conditions in crop-producing regions. "
                "Crop stress reduces yield expectations — bullish for grain prices.",
                TemporalLayer.T2,
            )

        # Cold snap — bullish for natural gas
        if cold_snap and is_energy:
            return (
                SignalDirection.BULLISH,
                0.70,
                "Cold snap / winter storm active — heating demand spike expected. "
                "Bullish for natural gas, mildly bullish for energy complex.",
                TemporalLayer.T1,
            )

        # Hurricane without energy domain — still relevant
        if hurricane:
            return (
                SignalDirection.BULLISH,
                0.55,
                "Active hurricane — may disrupt shipping and supply chains broadly.",
                TemporalLayer.T1,
            )

        # Moderate severe weather
        if severe_count > 5:
            return (
                SignalDirection.BULLISH,
                0.45,
                f"{severe_count} severe weather alerts active — elevated supply disruption risk.",
                TemporalLayer.T1,
            )

        # Clear skies
        return (
            SignalDirection.NEUTRAL,
            0.50,
            "No significant commodity-impacting weather events detected. "
            "Weather is not a factor in current cycle.",
            TemporalLayer.T1,
        )
