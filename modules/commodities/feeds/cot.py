"""
CFTC Commitment of Traders (COT) Feed
Free data from CFTC disaggregated futures reports.
No API key needed. Weekly release (Tuesday, data as of prior Tuesday).

The disaggregated report breaks positions into:
- Producer/Merchant (commercials — hedgers)
- Swap Dealers
- Managed Money (speculators — the crowd)
- Other Reportables

Key signal: when Managed Money is extremely long or short relative to
historical range, the trade is crowded and reversal risk rises.

Data source: CFTC disaggregated short format CSV
https://www.cftc.gov/dea/newcot/f_disagg.txt
"""

import csv
import io
import time
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from modules.commodities.feeds.base import BaseFeed, FeedResult


# CFTC contract codes for commodities we care about
# Maps domain_path suffix to CFTC market name substrings
COMMODITY_CONTRACTS = {
    "crude_oil":    "CRUDE OIL",
    "natural_gas":  "NAT GAS",
    "gold":         "GOLD",
    "silver":       "SILVER",
    "copper":       "COPPER",
    "wheat":        "WHEAT",
    "corn":         "CORN",
    "soy":          "SOYBEANS",
    "sugar":        "SUGAR",
}

# Historical percentile thresholds for extreme positioning
# If managed money net long is in top 20% of range → extreme long
# If in bottom 20% → extreme short
EXTREME_LONG_THRESHOLD = 0.80
EXTREME_SHORT_THRESHOLD = 0.20


class COTFeed(BaseFeed):
    """
    Fetches and parses CFTC Commitment of Traders disaggregated report.
    The short-format CSV is tab-delimited with headers.
    """

    def __init__(self, cache_ttl_seconds: int = 86400):
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)
        self._raw_cache: Optional[list[dict]] = None
        self._raw_cache_at: Optional[float] = None

    def _url(self, **kwargs) -> str:
        # Disaggregated futures-only, short format, current year
        return "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    def _headers(self) -> dict:
        return {"User-Agent": "WorldOracle/1.0"}

    def _parse(self, raw: dict) -> dict:
        # Not used — we override fetch() entirely
        return raw

    def _fetch_and_parse_csv(self) -> Optional[list[dict]]:
        """
        Fetch the CFTC disaggregated report and parse the CSV.
        Returns a list of row dicts, one per contract.
        """
        # Check raw cache
        if self._raw_cache and self._raw_cache_at:
            age = time.time() - self._raw_cache_at
            if age < self._cache_ttl:
                return self._raw_cache

        try:
            url = self._url()
            req = Request(url, headers=self._headers())
            with urlopen(req, timeout=30) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")

            # CFTC disaggregated short format has NO header row.
            # Parse as raw CSV and map by column index.
            reader = csv.reader(io.StringIO(raw_text))
            rows = []
            for raw_row in reader:
                if len(raw_row) < 18:
                    continue
                rows.append({
                    "Market_and_Exchange_Names": raw_row[0].strip(),
                    "As_of_Date_In_Form_YYMMDD": raw_row[1].strip(),
                    "Report_Date_as_YYYY-MM-DD": raw_row[2].strip(),
                    "Open_Interest_All": raw_row[7].strip(),
                    "Prod_Merc_Positions_Long_All": raw_row[8].strip(),
                    "Prod_Merc_Positions_Short_All": raw_row[9].strip(),
                    "M_Money_Positions_Long_All": raw_row[13].strip(),
                    "M_Money_Positions_Short_All": raw_row[14].strip(),
                    "M_Money_Positions_Spread_All": raw_row[15].strip(),
                })

            self._raw_cache = rows
            self._raw_cache_at = time.time()
            return rows

        except (URLError, HTTPError, Exception):
            return None

    def fetch(self, **kwargs) -> FeedResult:
        """
        Fetch COT data and extract positioning for a specific commodity.
        Pass commodity="crude_oil" (or other key from COMMODITY_CONTRACTS).
        """
        commodity = kwargs.get("commodity", "crude_oil")
        search_term = COMMODITY_CONTRACTS.get(commodity)

        if not search_term:
            return FeedResult(
                data={"available": False, "reason": f"No CFTC mapping for {commodity}"},
                ok=False,
                error=f"Unknown commodity: {commodity}",
            )

        rows = self._fetch_and_parse_csv()

        if rows is None:
            return FeedResult(
                ok=False,
                error="Failed to fetch CFTC disaggregated report",
            )

        # Find matching rows for this commodity
        matching = self._find_contract(rows, search_term)

        if not matching:
            return FeedResult(
                data={"available": False, "reason": f"No CFTC data found for '{search_term}'"},
                ok=True,
                fetched_at=self._raw_cache_at,
            )

        # Use the most recent matching row
        record = matching[0]

        # Extract positioning data
        try:
            data = self._extract_positioning(record, matching)
            return FeedResult(
                data=data,
                ok=True,
                fetched_at=self._raw_cache_at,
            )
        except (KeyError, ValueError, TypeError) as e:
            return FeedResult(
                data={"available": False, "reason": f"Parse error: {e}"},
                ok=True,
                fetched_at=self._raw_cache_at,
            )

    def _find_contract(self, rows: list[dict], search_term: str) -> list[dict]:
        """Find all rows matching a commodity search term."""
        matching = []
        for row in rows:
            market = row.get("Market_and_Exchange_Names", "")
            if search_term.upper() in market.upper():
                matching.append(row)
        return matching

    def _extract_positioning(self, record: dict, all_records: list[dict]) -> dict:
        """
        Extract managed money and commercial positioning from a COT record.
        The disaggregated format has these key columns:
        - M_Money_Positions_Long_All / M_Money_Positions_Short_All
        - Prod_Merc_Positions_Long_All / Prod_Merc_Positions_Short_All
        - Open_Interest_All
        """
        # Try multiple column name patterns (CFTC format varies slightly)
        mm_long = self._get_int(record, [
            "M_Money_Positions_Long_All",
            "M_Money_Positions_Long_ALL",
            "Money_Manager_Positions_Long_All",
        ])
        mm_short = self._get_int(record, [
            "M_Money_Positions_Short_All",
            "M_Money_Positions_Short_ALL",
            "Money_Manager_Positions_Short_All",
        ])
        prod_long = self._get_int(record, [
            "Prod_Merc_Positions_Long_All",
            "Prod_Merc_Positions_Long_ALL",
        ])
        prod_short = self._get_int(record, [
            "Prod_Merc_Positions_Short_All",
            "Prod_Merc_Positions_Short_ALL",
        ])
        oi = self._get_int(record, [
            "Open_Interest_All",
            "Open_Interest_ALL",
        ])

        report_date = record.get("Report_Date_as_YYYY-MM-DD", record.get("As_of_Date_In_Form_YYMMDD", ""))
        market_name = record.get("Market_and_Exchange_Names", "")

        # Calculate net positioning
        mm_net = (mm_long - mm_short) if mm_long is not None and mm_short is not None else None
        prod_net = (prod_long - prod_short) if prod_long is not None and prod_short is not None else None

        # Calculate managed money net as % of open interest
        mm_net_pct = None
        if mm_net is not None and oi and oi > 0:
            mm_net_pct = round((mm_net / oi) * 100, 2)

        # Determine extreme positioning using historical range from all matching records
        extreme = self._assess_extreme(mm_net, all_records)

        return {
            "available": True,
            "market": market_name,
            "report_date": report_date,
            "managed_money_long": mm_long,
            "managed_money_short": mm_short,
            "managed_money_net": mm_net,
            "managed_money_net_pct_oi": mm_net_pct,
            "producer_long": prod_long,
            "producer_short": prod_short,
            "producer_net": prod_net,
            "open_interest": oi,
            "extreme_positioning": extreme,
            "spec_net_long": mm_net,
        }

    def _get_int(self, record: dict, keys: list[str]) -> Optional[int]:
        """Try multiple column names, return first valid int."""
        for key in keys:
            val = record.get(key)
            if val is not None:
                try:
                    return int(str(val).strip().replace(",", ""))
                except (ValueError, TypeError):
                    continue
        return None

    def _assess_extreme(self, mm_net: Optional[int], all_records: list[dict]) -> Optional[str]:
        """
        Assess whether managed money positioning is extreme
        relative to the range of values in available records.
        """
        if mm_net is None or len(all_records) < 2:
            return None

        nets = []
        for r in all_records:
            long_val = self._get_int(r, ["M_Money_Positions_Long_All", "M_Money_Positions_Long_ALL", "Money_Manager_Positions_Long_All"])
            short_val = self._get_int(r, ["M_Money_Positions_Short_All", "M_Money_Positions_Short_ALL", "Money_Manager_Positions_Short_All"])
            if long_val is not None and short_val is not None:
                nets.append(long_val - short_val)

        if len(nets) < 2:
            return None

        min_net = min(nets)
        max_net = max(nets)
        if max_net == min_net:
            return None

        percentile = (mm_net - min_net) / (max_net - min_net)

        if percentile >= EXTREME_LONG_THRESHOLD:
            return "long"
        elif percentile <= EXTREME_SHORT_THRESHOLD:
            return "short"
        return None

    def health(self) -> dict:
        result = self.fetch(commodity="crude_oil")
        if result.ok and result.data and result.data.get("available"):
            return {"status": "ok", "last_fetched": result.fetched_at}
        if result.ok:
            return {"status": "partial", "message": result.data.get("reason", "Data not available")}
        return {"status": "error", "message": result.error}
