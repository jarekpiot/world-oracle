"""
Price Agent (T0) Tests — the heartbeat.
Tests price direction, confidence scaling, and ZERO FABRICATION.
Run: python -m pytest tests/test_price_agent.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

from core.registry import SignalDirection, TemporalLayer
from modules.commodities.feeds.base import FeedResult
from modules.commodities.feeds.price import PriceFeed
from modules.commodities.agents.price_agent import PriceAgent


DOMAIN = "commodity.energy.crude_oil"


class TestPriceFeed:

    def test_parse_valid_response(self):
        feed = PriceFeed()
        raw = {
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 99.05,
                        "chartPreviousClose": 95.00,
                        "regularMarketDayHigh": 100.20,
                        "regularMarketDayLow": 94.50,
                        "symbol": "CL=F",
                        "currency": "USD",
                    },
                    "timestamp": [],
                    "indicators": {"quote": [{"close": []}]},
                }]
            }
        }
        parsed = feed._parse(raw)
        assert parsed["price"] == 99.05
        assert parsed["previous"] == 95.00
        assert parsed["change"] == pytest.approx(4.05, abs=0.01)
        assert parsed["pct_change"] == pytest.approx(4.263, abs=0.01)

    def test_parse_empty_response(self):
        feed = PriceFeed()
        raw = {"chart": {"result": []}}
        parsed = feed._parse(raw)
        assert parsed["price"] is None
        assert parsed["change"] is None

    def test_health_checks_wti(self):
        feed = PriceFeed()
        feed._symbol_cache["CL=F"] = (
            FeedResult(data={"price": 99.05}, ok=True, fetched_at=1000.0),
            1000.0
        )
        # Would need live network; just test structure
        h = feed.health()
        assert "status" in h


class TestPriceAgent:

    def _make_feed(self, price, previous):
        feed = MagicMock(spec=PriceFeed)
        change = round(price - previous, 3) if previous else None
        pct = round((change / previous) * 100, 3) if change and previous else None
        feed.fetch.return_value = FeedResult(
            data={
                "price": price,
                "previous": previous,
                "change": change,
                "pct_change": pct,
                "unit": "USD/barrel",
                "source": "Yahoo Finance (live)",
                "period": "live",
                "readings": [],
            },
            ok=True,
            fetched_at=1000.0,
        )
        return feed

    @pytest.mark.asyncio
    async def test_large_up_move_is_bullish(self):
        feed = self._make_feed(75.0, 72.0)  # +4.2%
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.70
        assert signal.temporal_layer == TemporalLayer.T0

    @pytest.mark.asyncio
    async def test_moderate_up_move_is_bullish(self):
        feed = self._make_feed(72.0, 71.0)  # +1.4%
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.58

    @pytest.mark.asyncio
    async def test_small_up_move_is_bullish(self):
        feed = self._make_feed(71.5, 71.0)  # +0.7%
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.45

    @pytest.mark.asyncio
    async def test_flat_is_neutral(self):
        feed = self._make_feed(71.1, 71.0)  # +0.14%
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_large_down_move_is_bearish(self):
        feed = self._make_feed(68.0, 72.0)  # -5.6%
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.70

    @pytest.mark.asyncio
    async def test_moderate_down_move_is_bearish(self):
        feed = self._make_feed(70.0, 71.5)  # -2.1%
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.58

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        feed = MagicMock(spec=PriceFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="timeout")
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25
        assert signal.temporal_layer == TemporalLayer.T0

    @pytest.mark.asyncio
    async def test_has_decay_triggers(self):
        feed = self._make_feed(72.0, 70.0)
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert len(signal.decay_triggers) >= 2

    @pytest.mark.asyncio
    async def test_is_t0_layer(self):
        """Price agent must always produce T0 signals."""
        feed = self._make_feed(72.0, 70.0)
        agent = PriceAgent(feed)
        signal = await agent.run(DOMAIN)
        assert signal.temporal_layer == TemporalLayer.T0
