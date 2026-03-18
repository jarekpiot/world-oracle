"""
GDELT Geopolitical Events Feed
Free API: https://api.gdeltproject.org/api/v2/
No API key needed. 15-minute refresh.

RATE LIMITING: GDELT aggressively rate-limits (429 errors).
This feed uses:
  - Per-query cache with 15-minute TTL
  - Shared cache across all GDELT feed instances
  - Exponential backoff: 3 retries at 2s, 4s, 8s delays
"""

import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import json

from modules.commodities.feeds.base import BaseFeed, FeedResult


# Regions that matter most for commodity supply chains
COMMODITY_REGIONS = {
    "middle_east":  "Middle East",
    "ukraine":      "Ukraine Russia",
    "red_sea":      "Red Sea Houthi",
    "hormuz":       "Strait Hormuz Iran",
    "taiwan":       "Taiwan Strait China",
    "opec":         "OPEC output production",
}

# ── SHARED CACHE — all GDELTFeed instances share this ──────────────────────
# Key: query string, Value: (FeedResult, timestamp)
_GDELT_CACHE: dict[str, tuple[FeedResult, float]] = {}
_GDELT_CACHE_TTL = 900  # 15 minutes
_GDELT_LAST_REQUEST = 0.0  # global rate limit tracker
_GDELT_MIN_INTERVAL = 2.0  # minimum seconds between requests


class GDELTFeed(BaseFeed):
    """
    Fetches geopolitical event data from GDELT API v2.
    Measures tone (negative = escalation) and volume (article count).

    Uses a shared query-level cache and exponential backoff
    to avoid 429 rate limiting.
    """

    def __init__(self, cache_ttl_seconds: int = 900):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

    def _url(self, **kwargs) -> str:
        query = kwargs.get("query", "oil energy conflict sanctions")
        mode = kwargs.get("mode", "artlist")
        return (
            f"https://api.gdeltproject.org/api/v2/doc/doc"
            f"?query={query.replace(' ', '%20')}"
            f"&mode={mode}"
            f"&maxrecords=50"
            f"&timespan=7d"
            f"&format=json"
        )

    def _parse(self, raw: dict) -> dict:
        """
        Parse GDELT response into geopolitical signal data.
        Key metric: average tone (negative = conflict/tension).
        """
        articles = raw.get("articles", [])

        if not articles:
            return {
                "article_count": 0,
                "avg_tone": 0.0,
                "regions_mentioned": [],
                "escalation_score": 0.0,
            }

        tones = []
        region_hits = {region: 0 for region in COMMODITY_REGIONS}

        for article in articles:
            tone = article.get("tone", 0)
            if isinstance(tone, (int, float)):
                tones.append(tone)

            title = (article.get("title", "") + " " + article.get("seendate", "")).lower()
            for key, terms in COMMODITY_REGIONS.items():
                if any(t.lower() in title for t in terms.split()):
                    region_hits[key] += 1

        avg_tone = sum(tones) / len(tones) if tones else 0.0
        escalation = min(1.0, max(0.0, (-avg_tone) / 5.0))
        active_regions = [r for r, count in region_hits.items() if count > 0]

        return {
            "article_count": len(articles),
            "avg_tone": round(avg_tone, 3),
            "escalation_score": round(escalation, 3),
            "active_regions": active_regions,
            "region_hits": {r: c for r, c in region_hits.items() if c > 0},
        }

    def fetch(self, **kwargs) -> FeedResult:
        """
        Fetch with shared query-level cache and exponential backoff.
        """
        global _GDELT_LAST_REQUEST

        query = kwargs.get("query", "oil energy conflict sanctions")
        cache_key = query.strip().lower()

        # Check shared cache first
        if cache_key in _GDELT_CACHE:
            cached_result, cached_at = _GDELT_CACHE[cache_key]
            age = time.time() - cached_at
            if age < _GDELT_CACHE_TTL:
                return FeedResult(
                    data=cached_result.data,
                    ok=True,
                    fetched_at=cached_at,
                    cached=True,
                )

        # Global rate limit — wait if too soon since last request
        now = time.time()
        wait = _GDELT_MIN_INTERVAL - (now - _GDELT_LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)

        # Exponential backoff — 3 retries at 2s, 4s, 8s
        last_error = None
        for attempt in range(4):  # 0, 1, 2, 3
            if attempt > 0:
                delay = 2 ** attempt  # 2s, 4s, 8s
                time.sleep(delay)

            try:
                _GDELT_LAST_REQUEST = time.time()
                url = self._url(**kwargs)
                req = Request(url, headers=self._headers())
                with urlopen(req, timeout=15) as resp:
                    raw = json.loads(resp.read().decode())

                parsed = self._parse(raw)
                result = FeedResult(
                    data=parsed,
                    ok=True,
                    fetched_at=time.time(),
                )
                # Store in shared cache
                _GDELT_CACHE[cache_key] = (result, time.time())
                return result

            except HTTPError as e:
                last_error = f"HTTP error: {e}"
                if e.code == 429:
                    continue  # retry with backoff
                else:
                    break  # non-retryable
            except (URLError, json.JSONDecodeError, Exception) as e:
                last_error = f"Feed error: {e}"
                break  # non-retryable

        return FeedResult(ok=False, error=last_error)

    def fetch_region(self, region_key: str):
        """Fetch events for a specific commodity-relevant region."""
        query = COMMODITY_REGIONS.get(region_key, region_key)
        return self.fetch(query=query)

    def health(self) -> dict:
        result = self.fetch(query="oil energy")
        if result.ok:
            return {"status": "ok", "last_fetched": result.fetched_at}
        return {"status": "error", "message": result.error}
