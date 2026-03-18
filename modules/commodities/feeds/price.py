"""
Live Price Feed — T0 Heartbeat
Near-real-time commodity spot/futures prices via Yahoo Finance.
Free, no API key needed. Updates every few minutes during market hours.

Symbols:
  CL=F   WTI Crude Oil Futures
  BZ=F   Brent Crude Futures
  NG=F   Natural Gas Futures
  GC=F   Gold Futures
  SI=F   Silver Futures
  HG=F   Copper Futures
  ZW=F   Wheat Futures
  ZC=F   Corn Futures
  ZS=F   Soybean Futures
"""

import time
import json
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from modules.commodities.feeds.base import BaseFeed, FeedResult


# Map domain paths to Yahoo Finance symbols
DOMAIN_TO_SYMBOL = {
    "commodity.energy.crude_oil":       "CL=F",
    "commodity.energy.natural_gas":     "NG=F",
    "commodity.metals.gold":            "GC=F",
    "commodity.metals.silver":          "SI=F",
    "commodity.metals.copper":          "HG=F",
    "commodity.agriculture.wheat":      "ZW=F",
    "commodity.agriculture.corn":       "ZC=F",
    "commodity.agriculture.soy":        "ZS=F",
}

# Also support FX and crypto
FX_SYMBOLS = {
    "fx.major.eurusd": "EURUSD=X",
    "fx.major.usdjpy": "JPY=X",
    "fx.major.gbpusd": "GBPUSD=X",
}

CRYPTO_SYMBOLS = {
    "crypto.l1.bitcoin":  "BTC-USD",
    "crypto.l1.ethereum": "ETH-USD",
    "crypto.l1.solana":   "SOL-USD",
}

ALL_SYMBOLS = {**DOMAIN_TO_SYMBOL, **FX_SYMBOLS, **CRYPTO_SYMBOLS}


class PriceFeed(BaseFeed):
    """
    Near-real-time price feed via Yahoo Finance chart API.
    Cache TTL is 60s — T0 heartbeat frequency.
    Free, no API key needed.
    """

    def __init__(self, cache_ttl_seconds: int = 60):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)
        self._symbol_cache: dict[str, tuple[FeedResult, float]] = {}

    def _url(self, **kwargs) -> str:
        symbol = kwargs.get("symbol", "CL=F")
        return (
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?interval=5m&range=1d"
        )

    def _headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

    def _parse(self, raw: dict) -> dict:
        """Parse Yahoo Finance chart response into price data."""
        result = raw.get("chart", {}).get("result", [])
        if not result:
            return {"price": None, "previous": None, "change": None, "pct_change": None}

        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        day_high = meta.get("regularMarketDayHigh")
        day_low = meta.get("regularMarketDayLow")
        symbol = meta.get("symbol", "")
        currency = meta.get("currency", "USD")

        change = None
        pct_change = None
        if price is not None and prev_close is not None and prev_close != 0:
            change = round(price - prev_close, 3)
            pct_change = round((change / prev_close) * 100, 3)

        # Get intraday prices for trend
        timestamps = result[0].get("timestamp", [])
        closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        readings = []
        for i in range(min(5, len(timestamps))):
            if i < len(closes) and closes[-(i+1)] is not None:
                readings.append({"value": closes[-(i+1)]})

        return {
            "price": price,
            "previous": prev_close,
            "change": change,
            "pct_change": pct_change,
            "day_high": day_high,
            "day_low": day_low,
            "symbol": symbol,
            "currency": currency,
            "unit": f"{currency}/barrel" if "CL" in symbol or "BZ" in symbol else f"{currency}",
            "source": "Yahoo Finance (live)",
            "period": "live",
            "readings": readings,
        }

    def fetch(self, **kwargs) -> FeedResult:
        """Fetch with per-symbol caching."""
        domain = kwargs.get("domain", "")
        symbol = kwargs.get("symbol") or ALL_SYMBOLS.get(domain, "CL=F")

        # Check per-symbol cache
        if symbol in self._symbol_cache:
            cached, cached_at = self._symbol_cache[symbol]
            if time.time() - cached_at < self._cache_ttl:
                return FeedResult(data=cached.data, ok=True, fetched_at=cached_at, cached=True)

        try:
            url = self._url(symbol=symbol)
            req = Request(url, headers=self._headers())
            with urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode())

            parsed = self._parse(raw)
            result = FeedResult(data=parsed, ok=True, fetched_at=time.time())
            self._symbol_cache[symbol] = (result, time.time())
            return result

        except (URLError, HTTPError) as e:
            return FeedResult(ok=False, error=f"Yahoo Finance error: {e}")
        except Exception as e:
            return FeedResult(ok=False, error=f"Price feed error: {e}")

    def health(self) -> dict:
        result = self.fetch(symbol="CL=F")
        if result.ok and result.data and result.data.get("price"):
            return {"status": "ok", "last_fetched": result.fetched_at,
                    "message": f"WTI ${result.data['price']}"}
        return {"status": "error", "message": result.error or "No price data"}
