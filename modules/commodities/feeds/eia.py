"""
EIA Petroleum Feed — Weekly US crude oil inventory data.
Free API: https://api.eia.gov/v2/
Requires API key (free signup at eia.gov).

The single most important commodity data point:
  - Inventory DRAW (stocks falling) = bullish
  - Inventory BUILD (stocks rising) = bearish
"""

import os
from typing import Optional
from modules.commodities.feeds.base import BaseFeed


# EIA series for weekly US crude oil stocks (excluding SPR)
# Unit: thousand barrels
CRUDE_STOCKS_SERIES = "PET.WCESTUS1.W"


class EIAFeed(BaseFeed):
    """
    Fetches weekly US petroleum inventory data from EIA API v2.
    Primary signal: crude oil commercial stocks (excl. SPR).
    """

    def __init__(self, api_key: Optional[str] = None, cache_ttl_seconds: int = 3600):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)
        self.api_key = api_key or os.environ.get("EIA_API_KEY")

    def _url(self, **kwargs) -> str:
        if not self.api_key:
            raise ValueError("EIA_API_KEY not set")

        # Weekly petroleum stocks — US commercial crude excl SPR
        # Must filter by duoarea=NUS (national) AND series to avoid
        # mixing total stocks, SPR, transit, and regional PADDs
        return (
            f"https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
            f"?api_key={self.api_key}"
            f"&frequency=weekly"
            f"&data[0]=value"
            f"&facets[product][]={kwargs.get('product', 'EPC0')}"
            f"&facets[duoarea][]=NUS"
            f"&facets[process][]=SAX"
            f"&sort[0][column]=period"
            f"&sort[0][direction]=desc"
            f"&length={kwargs.get('length', 10)}"
        )

    def _parse(self, raw: dict) -> dict:
        """
        Parse EIA API v2 response into structured inventory data.
        Returns weekly stock levels and week-over-week change.
        """
        data_points = raw.get("response", {}).get("data", [])

        if not data_points:
            return {"readings": [], "latest": None, "change": None}

        readings = []
        for dp in data_points:
            readings.append({
                "period": dp.get("period"),
                "value":  dp.get("value"),  # thousand barrels
                "product": dp.get("product-name", "crude oil"),
            })

        latest = readings[0]["value"] if readings else None
        previous = readings[1]["value"] if len(readings) > 1 else None

        change = None
        if latest is not None and previous is not None:
            try:
                change = float(latest) - float(previous)
            except (TypeError, ValueError):
                change = None

        return {
            "readings": readings,
            "latest":   latest,
            "previous": previous,
            "change":   change,  # negative = draw (bullish), positive = build (bearish)
            "unit":     "thousand barrels",
            "series":   "weekly_crude_stocks_excl_spr",
        }

    def health(self) -> dict:
        """Quick health check — can we reach the API?"""
        if not self.api_key:
            return {"status": "no_api_key", "message": "EIA_API_KEY not configured"}
        result = self.fetch()
        if result.ok:
            return {"status": "ok", "last_fetched": result.fetched_at}
        return {"status": "error", "message": result.error}
