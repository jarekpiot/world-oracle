"""
CFTC Commitment of Traders (COT) Feed
Free data: https://www.cftc.gov/dea/futures/deacmesf.htm
No API key needed. Weekly release (Friday).

Shows how commercial hedgers vs speculators are positioned.
When speculators are extremely long → crowded trade → reversal risk.
When commercials are heavily hedged short → they expect lower prices.
"""

from modules.commodities.feeds.base import BaseFeed


# CFTC COT report URLs — machine-readable format
COT_FUTURES_URL = "https://www.cftc.gov/dea/futures/deacmesf.htm"


class COTFeed(BaseFeed):
    """
    Fetches CFTC Commitment of Traders positioning data.
    The COT report reveals how the smart money (commercials) vs
    speculative money (managed money) are positioned.

    Note: The raw CFTC data is in fixed-width text format.
    For the initial implementation, this feed returns a structured
    placeholder that agents can work with. A full parser for the
    CFTC bulk CSV would be added in a production build.
    """

    def __init__(self, cache_ttl_seconds: int = 86400):  # daily cache
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

    def _url(self, **kwargs) -> str:
        # CFTC provides bulk downloads — use the short format report
        return "https://www.cftc.gov/dea/newcot/deacmesf.txt"

    def _headers(self) -> dict:
        return {"User-Agent": "WorldOracle/1.0"}

    def _parse(self, raw) -> dict:
        """
        Parse COT data. The CFTC format is fixed-width text, not JSON.
        This feed handles the non-JSON response by extracting key fields.
        """
        # CFTC returns plain text, not JSON — the base fetch will fail
        # on json.loads. We handle this in a custom fetch override.
        # For now, return the raw data structure that agents expect.
        return {
            "available": False,
            "reason": "COT parser requires fixed-width text processing — pending implementation",
            "spec_net_long": None,
            "commercial_net_short": None,
            "extreme_positioning": None,
        }

    def fetch(self, **kwargs):
        """
        Override base fetch — CFTC data is not JSON.
        Returns structured placeholder until full parser is built.
        """
        return super().__new_result(
        ) if False else self._fallback_result()

    def _fallback_result(self):
        from modules.commodities.feeds.base import FeedResult
        return FeedResult(
            data=self._parse({}),
            ok=True,
            fetched_at=None,
        )

    def health(self) -> dict:
        return {
            "status": "partial",
            "message": "COT feed structured but full CFTC parser pending",
        }
