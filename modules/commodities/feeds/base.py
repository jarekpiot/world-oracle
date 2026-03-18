"""
Base feed class — every data feed inherits from this.
Handles HTTP, caching, staleness detection, and graceful failure.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import json


@dataclass
class FeedResult:
    """What every feed returns."""
    data:        Optional[dict] = None
    ok:          bool = False
    error:       Optional[str] = None
    fetched_at:  Optional[float] = None   # epoch seconds
    cached:      bool = False


class BaseFeed:
    """
    Base HTTP feed with caching and graceful failure.
    Subclasses implement _url() and _parse(raw_json).
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        self._cache: Optional[FeedResult] = None
        self._cache_ttl = cache_ttl_seconds

    def _url(self, **kwargs) -> str:
        raise NotImplementedError

    def _headers(self) -> dict:
        return {"User-Agent": "WorldOracle/1.0", "Accept": "application/json"}

    def _parse(self, raw: dict) -> dict:
        """Transform raw API response into the shape agents expect."""
        raise NotImplementedError

    def fetch(self, **kwargs) -> FeedResult:
        """
        Fetch data from the feed. Returns cached result if still fresh.
        Never raises — returns FeedResult with ok=False on failure.
        """
        # Check cache
        if self._cache and self._cache.ok:
            age = time.time() - (self._cache.fetched_at or 0)
            if age < self._cache_ttl:
                return FeedResult(
                    data=self._cache.data,
                    ok=True,
                    fetched_at=self._cache.fetched_at,
                    cached=True,
                )

        try:
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
            self._cache = result
            return result

        except (URLError, HTTPError) as e:
            return FeedResult(ok=False, error=f"HTTP error: {e}")
        except json.JSONDecodeError as e:
            return FeedResult(ok=False, error=f"JSON parse error: {e}")
        except Exception as e:
            return FeedResult(ok=False, error=f"Feed error: {e}")

    def is_stale(self, max_age_seconds: float) -> bool:
        if not self._cache or not self._cache.fetched_at:
            return True
        return (time.time() - self._cache.fetched_at) > max_age_seconds
