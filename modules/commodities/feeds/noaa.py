"""
NOAA Weather Feed
Free API: https://api.weather.gov/
No API key needed. 6-hour refresh.

Tracks weather events that impact commodity supply:
- Hurricanes in Gulf of Mexico (oil production shutdowns)
- Drought in US Midwest (crop stress)
- Cold snaps (natural gas demand spikes)
"""

from modules.commodities.feeds.base import BaseFeed


# NOAA alert zones relevant to commodity supply
COMMODITY_ZONES = {
    "gulf_of_mexico": "GM",      # hurricane → oil production
    "midwest_crops":  "MW",      # drought → grain prices
    "natural_gas":    "NE",      # cold snap → nat gas demand
}


class NOAAFeed(BaseFeed):
    """
    Fetches active weather alerts from NOAA API.
    Focuses on events that disrupt commodity supply chains.
    """

    def __init__(self, cache_ttl_seconds: int = 3600):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

    def _url(self, **kwargs) -> str:
        # Active alerts for the US — filtered by severity
        severity = kwargs.get("severity", "severe,extreme")
        return (
            f"https://api.weather.gov/alerts/active"
            f"?status=actual"
            f"&severity={severity}"
        )

    def _headers(self) -> dict:
        return {
            "User-Agent": "WorldOracle/1.0 (commodity-weather-monitor)",
            "Accept": "application/geo+json",
        }

    def _parse(self, raw: dict) -> dict:
        """
        Parse NOAA alerts into commodity-relevant weather signals.
        """
        features = raw.get("features", [])

        if not features:
            return {
                "alert_count": 0,
                "severe_count": 0,
                "hurricane_active": False,
                "drought_active": False,
                "cold_snap_active": False,
                "alerts": [],
            }

        hurricane_keywords = {"hurricane", "tropical storm", "tropical cyclone"}
        drought_keywords = {"drought", "excessive heat", "heat wave"}
        cold_keywords = {"freeze", "winter storm", "blizzard", "cold", "ice storm"}

        alerts = []
        hurricane_active = False
        drought_active = False
        cold_snap_active = False
        severe_count = 0

        for feature in features[:30]:  # cap to avoid huge payloads
            props = feature.get("properties", {})
            event = props.get("event", "").lower()
            severity = props.get("severity", "").lower()
            headline = props.get("headline", "")
            area = props.get("areaDesc", "")

            if severity in ("severe", "extreme"):
                severe_count += 1

            if any(k in event for k in hurricane_keywords):
                hurricane_active = True
            if any(k in event for k in drought_keywords):
                drought_active = True
            if any(k in event for k in cold_keywords):
                cold_snap_active = True

            alerts.append({
                "event": props.get("event", ""),
                "severity": severity,
                "headline": headline[:120],
                "area": area[:100],
            })

        return {
            "alert_count": len(features),
            "severe_count": severe_count,
            "hurricane_active": hurricane_active,
            "drought_active": drought_active,
            "cold_snap_active": cold_snap_active,
            "alerts": alerts[:10],  # top 10 only
        }

    def health(self) -> dict:
        result = self.fetch()
        if result.ok:
            return {"status": "ok", "last_fetched": result.fetched_at}
        return {"status": "error", "message": result.error}
