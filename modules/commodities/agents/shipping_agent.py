"""
Shipping Agent — T1/T2
Physical trade flow — the circulatory system of global commodities.

Rising freight rates / Baltic Dry = real physical demand (bullish).
Falling freight rates = demand softening (bearish).
Route disruptions (Red Sea, Hormuz) = supply chain stress (bullish energy).

Connects to: Baltic Dry Index (pending paid feed)
Confidence range: 0.30–0.78
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from modules.commodities.feeds.baltic import BalticDryFeed


class ShippingAgent:
    """
    Reads shipping and freight data to gauge real physical commodity demand.
    The Baltic Dry Index is a leading indicator — ships don't lie.
    """

    AGENT_ID = "shipping_agent"

    def __init__(self, baltic_feed: BalticDryFeed):
        self.feed = baltic_feed
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Fetch shipping data and produce a signal.
        Currently returns UNKNOWN — BDI feed requires paid data source.
        """
        result = self.feed.fetch()

        if not result.ok or not result.data:
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="Baltic Dry Index (not connected)",
                value={"status": "feed_unavailable"},
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["Baltic Dry feed connected"],
                reasoning="Baltic Dry Index feed not connected — requires paid data provider. "
                          "No shipping signal this cycle.",
            )

        data = result.data

        # When BDI data is available, interpret it
        if not data.get("available", False):
            return self.temporal.tag_signal(
                agent_id=self.AGENT_ID,
                source="Baltic Dry Index (pending)",
                value=data,
                direction=SignalDirection.UNKNOWN,
                confidence=0.25,
                layer=TemporalLayer.T2,
                domain_path=domain_path,
                decay_triggers=["BDI data source connected"],
                reasoning="BDI data source pending — no shipping signal available.",
            )

        # Future: interpret BDI levels and changes
        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="Baltic Dry Index",
            value=data,
            direction=SignalDirection.UNKNOWN,
            confidence=0.30,
            layer=TemporalLayer.T2,
            domain_path=domain_path,
            decay_triggers=[
                "Major shipping route reopens (e.g. Red Sea)",
                "New trade sanctions disrupting maritime flow",
                "BDI reversal >15% in one week",
            ],
            reasoning="BDI data received but interpretation pending.",
            raw_data=data,
        )
