"""
On-chain Agent — T1/T2
The blockchain doesn't lie — but we can't read it yet.

This agent would track:
  Exchange flows    → coins moving to/from exchanges (sell/buy pressure)
  Whale movements   → large holder activity (smart money signal)
  Active addresses  → network health and adoption momentum
  Hash rate         → miner conviction (Bitcoin-specific)
  DeFi TVL          → capital allocation in decentralised finance

No live feed yet. Returns UNKNOWN honestly with low confidence.
ZERO FABRICATION — we don't pretend to have data we don't have.

Confidence range: 0.25 (fixed — no data source)
"""

from core.registry import Signal, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine


class OnchainAgent:
    """
    On-chain metrics proxy.
    No live feed yet — returns UNKNOWN honestly.
    When a feed is wired (Glassnode, Dune, etc.), this agent
    becomes one of crypto's strongest signals.
    """

    AGENT_ID = "onchain_agent"

    def __init__(self):
        self.temporal = TemporalEngine()

    async def run(self, domain_path: str) -> Signal:
        """
        Return UNKNOWN — no on-chain data source connected yet.
        Honest about what we don't know.
        """
        asset = domain_path.split(".")[-1] if "." in domain_path else "unknown"

        return self.temporal.tag_signal(
            agent_id=self.AGENT_ID,
            source="On-chain metrics (pending)",
            value={
                "status": "no_feed",
                "pending_metrics": [
                    "exchange_net_flow",
                    "whale_transactions",
                    "active_addresses",
                    "hash_rate" if asset == "bitcoin" else "tvl",
                ],
                "candidate_feeds": [
                    "Glassnode",
                    "Dune Analytics",
                    "CryptoQuant",
                ],
            },
            direction=SignalDirection.UNKNOWN,
            confidence=0.25,
            layer=TemporalLayer.T1,
            domain_path=domain_path,
            decay_triggers=[
                "On-chain feed connected and returning live data",
                "Alternative on-chain data source identified",
                "Manual override by Oracle Team with external analysis",
            ],
            reasoning=f"On-chain metrics feed not yet connected for {asset}. "
                      f"Would track exchange flows, whale movements, and active addresses. "
                      f"Returning UNKNOWN — zero fabrication policy.",
            valid_horizon="48 hours",
        )
