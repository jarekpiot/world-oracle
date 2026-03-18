"""
World Oracle — Temporal Engine
Every signal has a birthday and an expiry.
The world breathes at four frequencies — this engine tracks all of them simultaneously.

The key insight: a T1 weather signal and a T2 supply signal are NOT in conflict.
They answer different questions about different horizons. The engine holds both.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from core.registry import Signal, TemporalLayer, SignalDirection


# Default validity windows per temporal layer
# These are starting points — modules can override per signal
LAYER_VALIDITY = {
    TemporalLayer.T0: timedelta(minutes=30),
    TemporalLayer.T1: timedelta(hours=48),
    TemporalLayer.T2: timedelta(weeks=8),
    TemporalLayer.T3: timedelta(days=548),   # ~18 months
}

LAYER_VALIDITY_HUMAN = {
    TemporalLayer.T0: "30 minutes",
    TemporalLayer.T1: "48 hours",
    TemporalLayer.T2: "8 weeks",
    TemporalLayer.T3: "18 months",
}

# How often each layer's data should be refreshed
LAYER_REFRESH = {
    TemporalLayer.T0: "60 seconds",
    TemporalLayer.T1: "6 hours",
    TemporalLayer.T2: "weekly",
    TemporalLayer.T3: "monthly",
}


class TemporalEngine:
    """
    Manages signal lifecycles across all four breathing frequencies.
    Knows the difference between a dead signal and a conflicting one.
    """

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def tag_signal(
        self,
        agent_id:        str,
        source:          str,
        value:           object,
        direction:       SignalDirection,
        confidence:      float,
        layer:           TemporalLayer,
        domain_path:     str,
        decay_triggers:  list[str],
        reasoning:       str = "",
        raw_data:        Optional[dict] = None,
        valid_horizon:   Optional[str] = None,
    ) -> Signal:
        """
        Create a fully-tagged signal with temporal metadata.
        Called by every agent before returning its output.
        """
        return Signal(
            agent_id=agent_id,
            source=source,
            value=value,
            direction=direction,
            confidence=confidence,
            temporal_layer=layer,
            generated_at=self.now_iso(),
            valid_horizon=valid_horizon or LAYER_VALIDITY_HUMAN[layer],
            decay_triggers=decay_triggers,
            domain_path=domain_path,
            reasoning=reasoning,
            raw_data=raw_data,
        )

    def is_valid(self, signal: Signal) -> bool:
        """
        Has this signal expired by time alone?
        Does not check decay triggers — that requires domain knowledge.
        """
        try:
            generated = datetime.fromisoformat(signal.generated_at)
        except ValueError:
            return False
        window = LAYER_VALIDITY[signal.temporal_layer]
        return (datetime.now(timezone.utc) - generated) < window

    def are_conflicting(self, s1: Signal, s2: Signal) -> bool:
        """
        Two signals conflict ONLY if they:
        1. Are on the same temporal layer (same horizon)
        2. Point in opposite directions (one bullish, one bearish)

        A T1 weather bearish and a T2 supply bullish = NOT a conflict.
        They answer different time horizon questions. Hold both.
        """
        if s1.temporal_layer != s2.temporal_layer:
            return False
        opposite_pairs = [
            {SignalDirection.BULLISH, SignalDirection.BEARISH}
        ]
        return {s1.direction, s2.direction} in opposite_pairs

    def layer_summary(self, signals: list[Signal]) -> dict:
        """
        Summarise signal coverage across temporal layers.
        Shows where the oracle has evidence and where it's blind.
        """
        summary = {layer: [] for layer in TemporalLayer}
        for s in signals:
            summary[s.temporal_layer].append({
                "agent": s.agent_id,
                "direction": s.direction.value,
                "confidence": s.confidence,
                "valid": self.is_valid(s),
            })
        return {k.value: v for k, v in summary.items()}

    def decay_summary(self, signals: list[Signal]) -> dict:
        """
        What decay triggers are active across all signals?
        Sorted by how many signals each trigger would invalidate.
        Helps the oracle know its biggest single points of failure.
        """
        trigger_counts: dict[str, int] = {}
        for s in signals:
            for trigger in s.decay_triggers:
                trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1
        return dict(sorted(trigger_counts.items(), key=lambda x: x[1], reverse=True))

    def build_reasoning_trace(self, signals: list[Signal]) -> dict:
        """
        Build the T3 → T2 → T1 → T0 reasoning chain.
        This is Layer 4 output — the oracle shows its working.
        """
        trace = {}
        for layer in [TemporalLayer.T3, TemporalLayer.T2,
                      TemporalLayer.T1, TemporalLayer.T0]:
            layer_signals = [s for s in signals if s.temporal_layer == layer]
            if not layer_signals:
                trace[layer.value] = {"status": "no signal", "confidence": None}
                continue
            directions = [s.direction for s in layer_signals]
            dominant = max(set(directions), key=directions.count)
            avg_conf = sum(s.confidence for s in layer_signals) / len(layer_signals)
            trace[layer.value] = {
                "status": dominant.value,
                "confidence": round(avg_conf, 3),
                "agents": [s.agent_id for s in layer_signals],
                "reasoning": "; ".join(s.reasoning for s in layer_signals if s.reasoning)[:200],
            }
        return trace

    def alignment_score(self, signals: list[Signal]) -> float:
        """
        How aligned are signals across temporal layers?
        All four layers pointing same direction = 1.0
        Total disagreement = 0.0
        This is separate from confidence — it measures internal consistency.
        """
        layer_directions = {}
        for s in signals:
            if s.temporal_layer not in layer_directions:
                layer_directions[s.temporal_layer] = []
            layer_directions[s.temporal_layer].append(s.direction)

        if not layer_directions:
            return 0.0

        layer_verdicts = []
        for layer, dirs in layer_directions.items():
            bullish = dirs.count(SignalDirection.BULLISH)
            bearish = dirs.count(SignalDirection.BEARISH)
            if bullish == bearish:
                # True split — count as neither direction
                layer_verdicts.append(SignalDirection.NEUTRAL)
                continue
            dominant = SignalDirection.BULLISH if bullish > bearish else SignalDirection.BEARISH
            layer_verdicts.append(dominant)

        directional = [v for v in layer_verdicts
                       if v in (SignalDirection.BULLISH, SignalDirection.BEARISH)]
        if not directional:
            return 0.0

        majority = max(set(directional), key=directional.count)
        aligned = sum(1 for v in directional if v == majority)
        return round(aligned / len(directional), 3)
