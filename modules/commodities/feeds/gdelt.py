"""
GDELT Geopolitical Events Feed
Free API: https://api.gdeltproject.org/api/v2/
No API key needed. 15-minute refresh.

Reads geopolitical event tone and volume for key commodity-impacting regions.
"""

from modules.commodities.feeds.base import BaseFeed


# Regions that matter most for commodity supply chains
COMMODITY_REGIONS = {
    "middle_east":  "Middle East",
    "ukraine":      "Ukraine Russia",
    "red_sea":      "Red Sea Houthi",
    "hormuz":       "Strait Hormuz Iran",
    "taiwan":       "Taiwan Strait China",
    "opec":         "OPEC output production",
}


class GDELTFeed(BaseFeed):
    """
    Fetches geopolitical event data from GDELT API v2.
    Measures tone (negative = escalation) and volume (article count).
    """

    def __init__(self, cache_ttl_seconds: int = 900):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

    def _url(self, **kwargs) -> str:
        query = kwargs.get("query", "oil energy conflict sanctions")
        mode = kwargs.get("mode", "artlist")
        # GDELT DOC API — returns article metadata with tone scores
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

        # Escalation score: 0 = calm, 1 = extreme tension
        # GDELT tone ranges roughly -10 to +10, negative = bad
        escalation = min(1.0, max(0.0, (-avg_tone) / 5.0))

        active_regions = [r for r, count in region_hits.items() if count > 0]

        return {
            "article_count": len(articles),
            "avg_tone": round(avg_tone, 3),
            "escalation_score": round(escalation, 3),
            "active_regions": active_regions,
            "region_hits": {r: c for r, c in region_hits.items() if c > 0},
        }

    def fetch_region(self, region_key: str):
        """Fetch events for a specific commodity-relevant region."""
        query = COMMODITY_REGIONS.get(region_key, region_key)
        return self.fetch(query=query)

    def health(self) -> dict:
        result = self.fetch(query="oil energy")
        if result.ok:
            return {"status": "ok", "last_fetched": result.fetched_at}
        return {"status": "error", "message": result.error}
