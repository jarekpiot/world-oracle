"""
Weather Agent — T1/T2
Weather is nature's breath — hurricanes, droughts, cold snaps all move commodities.

  Hurricane in Gulf → oil production shutdowns → bullish energy
  Drought in Midwest → crop stress → bullish agriculture
  Cold snap → nat gas demand spike → bullish energy

Connects to: NOAA weather alerts
Confidence range: 0.40–0.80
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.noaa import NOAAFeed


class WeatherAgent:
    """
    Reads NOAA weather alerts and maps supply-disrupting weather to commodity signals.
    """

    AGENT_ID = "weather_agent"

    def __init__(self, noaa_feed: NOAAFeed):
        self.feed = noaa_feed
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
        direction, confidence, reasoning, layer = self._interpret(data, domain_path)

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
            decay_triggers=[
                "Hurricane/storm system dissipates",
                "Drought conditions ease with rainfall",
                "Temperature normalisation forecast",
                "NOAA downgrades severity of active alerts",
            ],
            reasoning=reasoning,
            raw_data=data,
        )

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
