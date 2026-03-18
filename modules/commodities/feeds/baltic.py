"""
Baltic Dry Index Feed
The BDI measures the cost of shipping raw materials by sea.
Rising BDI = real demand for physical commodities (bullish).
Falling BDI = demand softening (bearish).

No free real-time API exists — this feed scrapes publicly available data.
For production, a paid data provider (e.g. Clarksons, Freightos) would be used.
"""

from modules.commodities.feeds.base import BaseFeed, FeedResult


class BalticDryFeed(BaseFeed):
    """
    Baltic Dry Index feed.
    Currently returns a structured placeholder — the BDI has no free JSON API.
    Production implementation would use a paid shipping data provider or scraper.
    """

    def __init__(self, cache_ttl_seconds: int = 86400):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

    def _url(self, **kwargs) -> str:
        # No free JSON API for BDI
        return ""

    def _parse(self, raw: dict) -> dict:
        return {"available": False, "reason": "No free BDI API — pending data provider"}

    def fetch(self, **kwargs) -> FeedResult:
        """BDI has no free API — return structured unavailable result."""
        return FeedResult(
            data={"available": False, "reason": "No free BDI API — pending data provider"},
            ok=False,
            error="Baltic Dry Index requires paid data source — not yet connected",
        )

    def health(self) -> dict:
        return {
            "status": "not_connected",
            "message": "BDI feed requires paid data provider",
        }
