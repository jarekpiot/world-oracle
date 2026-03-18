"""
Live Price Feed — T0 Heartbeat
Free commodity price data via Open Exchange / public APIs.

For crude oil, we use the U.S. Energy Information Administration's
spot price series, and as a fallback, publicly available price data.

This is the heartbeat — what is price doing RIGHT NOW?
"""

import os
from modules.commodities.feeds.base import BaseFeed


class PriceFeed(BaseFeed):
    """
    Fetches near-realtime commodity spot prices.
    Uses EIA API for petroleum spot prices (same key as inventory feed).
    Cache TTL is short (60s) because this is the heartbeat.
    """

    def __init__(self, api_key=None, cache_ttl_seconds: int = 60):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)
        self.api_key = api_key or os.environ.get("EIA_API_KEY")

    def _url(self, **kwargs) -> str:
        if not self.api_key:
            raise ValueError("EIA_API_KEY not set")

        product = kwargs.get("product", "RWTC")  # WTI Crude spot
        # EIA spot prices — daily, last 5 data points for trend
        return (
            f"https://api.eia.gov/v2/petroleum/pri/spt/data/"
            f"?api_key={self.api_key}"
            f"&frequency=daily"
            f"&data[0]=value"
            f"&facets[series][]={product}"
            f"&sort[0][column]=period"
            f"&sort[0][direction]=desc"
            f"&length={kwargs.get('length', 5)}"
        )

    def _parse(self, raw: dict) -> dict:
        """
        Parse EIA spot price response.
        Returns current price, previous price, and change.
        """
        data_points = raw.get("response", {}).get("data", [])

        if not data_points:
            return {"price": None, "previous": None, "change": None, "pct_change": None}

        readings = []
        for dp in data_points:
            try:
                val = float(dp.get("value", 0))
            except (TypeError, ValueError):
                continue
            readings.append({
                "period": dp.get("period"),
                "price": val,
                "series": dp.get("series-description", ""),
            })

        if not readings:
            return {"price": None, "previous": None, "change": None, "pct_change": None}

        price = readings[0]["price"]
        previous = readings[1]["price"] if len(readings) > 1 else None

        change = None
        pct_change = None
        if price is not None and previous is not None and previous != 0:
            change = round(price - previous, 3)
            pct_change = round((change / previous) * 100, 3)

        return {
            "price": price,
            "previous": previous,
            "change": change,
            "pct_change": pct_change,
            "unit": "USD/barrel",
            "series": readings[0].get("series", "WTI Crude"),
            "period": readings[0].get("period"),
            "readings": readings,
        }

    def health(self) -> dict:
        if not self.api_key:
            return {"status": "no_api_key", "message": "EIA_API_KEY not configured"}
        result = self.fetch()
        if result.ok:
            return {"status": "ok", "last_fetched": result.fetched_at}
        return {"status": "error", "message": result.error}
