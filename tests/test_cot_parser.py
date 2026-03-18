"""
CFTC COT Parser & Positioning Agent Tests
Tests the CSV parser, positioning interpretation, and ZERO FABRICATION.
Run: python -m pytest tests/test_cot_parser.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

from core.registry import SignalDirection, TemporalLayer
from modules.commodities.feeds.base import FeedResult
from modules.commodities.feeds.cot import COTFeed, COMMODITY_CONTRACTS
from modules.commodities.agents.positioning_agent import PositioningAgent


# ─── COT Feed Tests ─────────────────────────────────────────────────────────

class TestCOTFeed:

    def _make_rows(self, mm_long=200000, mm_short=150000, oi=500000):
        """Create mock CFTC CSV rows."""
        return [
            {
                "Market_and_Exchange_Names": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
                "Report_Date_as_YYYY-MM-DD": "2025-03-11",
                "M_Money_Positions_Long_All": str(mm_long),
                "M_Money_Positions_Short_All": str(mm_short),
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": str(oi),
            },
            # Second row for range calculation
            {
                "Market_and_Exchange_Names": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
                "Report_Date_as_YYYY-MM-DD": "2025-03-04",
                "M_Money_Positions_Long_All": str(mm_long - 20000),
                "M_Money_Positions_Short_All": str(mm_short + 10000),
                "Prod_Merc_Positions_Long_All": "95000",
                "Prod_Merc_Positions_Short_All": "175000",
                "Open_Interest_All": str(oi),
            },
        ]

    def test_extract_positioning(self):
        feed = COTFeed()
        rows = self._make_rows(mm_long=200000, mm_short=150000, oi=500000)
        data = feed._extract_positioning(rows[0], rows)
        assert data["available"] is True
        assert data["managed_money_long"] == 200000
        assert data["managed_money_short"] == 150000
        assert data["managed_money_net"] == 50000
        assert data["open_interest"] == 500000
        assert data["managed_money_net_pct_oi"] == 10.0  # 50k/500k * 100

    def test_find_contract_crude_oil(self):
        feed = COTFeed()
        rows = self._make_rows()
        rows.append({
            "Market_and_Exchange_Names": "NATURAL GAS - NYMEX",
            "M_Money_Positions_Long_All": "100",
            "M_Money_Positions_Short_All": "200",
        })
        matching = feed._find_contract(rows, "CRUDE OIL")
        assert len(matching) == 2  # both crude rows, not nat gas

    def test_find_contract_no_match(self):
        feed = COTFeed()
        rows = self._make_rows()
        matching = feed._find_contract(rows, "UNOBTANIUM")
        assert len(matching) == 0

    def test_extreme_long_detection(self):
        feed = COTFeed()
        # Make the first row have much higher net than second
        rows = [
            {
                "Market_and_Exchange_Names": "CRUDE OIL",
                "M_Money_Positions_Long_All": "300000",
                "M_Money_Positions_Short_All": "100000",  # net = +200k
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
                "Report_Date_as_YYYY-MM-DD": "2025-03-11",
            },
            {
                "Market_and_Exchange_Names": "CRUDE OIL",
                "M_Money_Positions_Long_All": "150000",
                "M_Money_Positions_Short_All": "150000",  # net = 0
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
                "Report_Date_as_YYYY-MM-DD": "2025-03-04",
            },
        ]
        data = feed._extract_positioning(rows[0], rows)
        assert data["extreme_positioning"] == "long"

    def test_extreme_short_detection(self):
        feed = COTFeed()
        rows = [
            {
                "Market_and_Exchange_Names": "CRUDE OIL",
                "M_Money_Positions_Long_All": "100000",
                "M_Money_Positions_Short_All": "300000",  # net = -200k
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
                "Report_Date_as_YYYY-MM-DD": "2025-03-11",
            },
            {
                "Market_and_Exchange_Names": "CRUDE OIL",
                "M_Money_Positions_Long_All": "150000",
                "M_Money_Positions_Short_All": "150000",  # net = 0
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
                "Report_Date_as_YYYY-MM-DD": "2025-03-04",
            },
        ]
        data = feed._extract_positioning(rows[0], rows)
        assert data["extreme_positioning"] == "short"

    def test_balanced_no_extreme(self):
        feed = COTFeed()
        # Row 1: net = 160k - 150k = 10k
        # Row 2 (from helper): net = (160k-20k) - (150k+10k) = 140k - 160k = -20k
        # Range: -20k to 10k, current at 10k = percentile 1.0... still extreme
        # Need 3 rows to create a wider range where middle is not extreme
        rows = [
            {
                "Market_and_Exchange_Names": "CRUDE OIL, LIGHT SWEET - NYMEX",
                "Report_Date_as_YYYY-MM-DD": "2025-03-11",
                "M_Money_Positions_Long_All": "165000",
                "M_Money_Positions_Short_All": "150000",  # net = 15k (middle)
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
            },
            {
                "Market_and_Exchange_Names": "CRUDE OIL, LIGHT SWEET - NYMEX",
                "Report_Date_as_YYYY-MM-DD": "2025-03-04",
                "M_Money_Positions_Long_All": "200000",
                "M_Money_Positions_Short_All": "150000",  # net = 50k (high)
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
            },
            {
                "Market_and_Exchange_Names": "CRUDE OIL, LIGHT SWEET - NYMEX",
                "Report_Date_as_YYYY-MM-DD": "2025-02-25",
                "M_Money_Positions_Long_All": "120000",
                "M_Money_Positions_Short_All": "150000",  # net = -30k (low)
                "Prod_Merc_Positions_Long_All": "100000",
                "Prod_Merc_Positions_Short_All": "180000",
                "Open_Interest_All": "500000",
            },
        ]
        data = feed._extract_positioning(rows[0], rows)
        # net = 15k, range = -30k to 50k, percentile = 45k/80k = 0.5625 → not extreme
        assert data["extreme_positioning"] is None

    def test_commodity_contracts_mapping(self):
        """All expected commodities have CFTC mappings."""
        assert "crude_oil" in COMMODITY_CONTRACTS
        assert "natural_gas" in COMMODITY_CONTRACTS
        assert "gold" in COMMODITY_CONTRACTS
        assert "wheat" in COMMODITY_CONTRACTS

    def test_fetch_unknown_commodity(self):
        feed = COTFeed()
        result = feed.fetch(commodity="unobtanium")
        assert result.ok is False
        assert "Unknown" in result.error

    def test_get_int_handles_commas(self):
        feed = COTFeed()
        record = {"key": "1,234,567"}
        assert feed._get_int(record, ["key"]) == 1234567

    def test_get_int_handles_missing(self):
        feed = COTFeed()
        record = {}
        assert feed._get_int(record, ["missing_key"]) is None


# ─── Positioning Agent Tests ────────────────────────────────────────────────

class TestPositioningAgentWithParser:

    def _make_feed_result(self, mm_net, extreme=None, mm_pct=10.0):
        feed = MagicMock(spec=COTFeed)
        feed.fetch.return_value = FeedResult(
            data={
                "available": True,
                "market": "CRUDE OIL, LIGHT SWEET",
                "report_date": "2025-03-11",
                "managed_money_long": max(0, mm_net) + 100000,
                "managed_money_short": 100000 - min(0, mm_net),
                "managed_money_net": mm_net,
                "managed_money_net_pct_oi": mm_pct,
                "producer_long": 100000,
                "producer_short": 180000,
                "producer_net": -80000,
                "open_interest": 500000,
                "extreme_positioning": extreme,
                "spec_net_long": mm_net,
            },
            ok=True,
            fetched_at=1000.0,
        )
        return feed

    @pytest.mark.asyncio
    async def test_extreme_long_is_bearish(self):
        """Crowded long = reversal risk = bearish."""
        feed = self._make_feed_result(mm_net=200000, extreme="long")
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BEARISH
        assert signal.confidence == 0.68
        assert "crowded" in signal.reasoning.lower() or "extremely long" in signal.reasoning.lower()

    @pytest.mark.asyncio
    async def test_extreme_short_is_bullish(self):
        """Washed out short = bounce risk = bullish."""
        feed = self._make_feed_result(mm_net=-200000, extreme="short")
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.BULLISH
        assert signal.confidence == 0.68

    @pytest.mark.asyncio
    async def test_balanced_is_neutral(self):
        feed = self._make_feed_result(mm_net=25000, extreme=None)
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.confidence == 0.50

    @pytest.mark.asyncio
    async def test_feed_failure_returns_unknown(self):
        """ZERO FABRICATION — feed down = UNKNOWN."""
        feed = MagicMock(spec=COTFeed)
        feed.fetch.return_value = FeedResult(ok=False, error="connection timeout")
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25

    @pytest.mark.asyncio
    async def test_no_data_returns_unknown(self):
        """No CFTC data for this commodity = UNKNOWN."""
        feed = MagicMock(spec=COTFeed)
        feed.fetch.return_value = FeedResult(
            data={"available": False, "reason": "No data found"},
            ok=True,
            fetched_at=1000.0,
        )
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.direction == SignalDirection.UNKNOWN
        assert signal.confidence == 0.25

    @pytest.mark.asyncio
    async def test_has_specific_decay_triggers(self):
        feed = self._make_feed_result(mm_net=200000, extreme="long")
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert len(signal.decay_triggers) >= 2
        assert any("15%" in t or "COT" in t for t in signal.decay_triggers)

    @pytest.mark.asyncio
    async def test_signal_is_t2(self):
        feed = self._make_feed_result(mm_net=25000)
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert signal.temporal_layer == TemporalLayer.T2

    @pytest.mark.asyncio
    async def test_includes_report_date_in_reasoning(self):
        feed = self._make_feed_result(mm_net=25000)
        agent = PositioningAgent(feed)
        signal = await agent.run("commodity.energy.crude_oil")
        assert "2025-03-11" in signal.reasoning
