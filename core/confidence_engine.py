"""
World Oracle — Confidence Engine
Scores, gates, and — crucially — abstains.

The oracle's ability to say "insufficient signal" is as important as its ability
to answer. A system that always produces an answer is dangerous.
This is the ZERO FABRICATION rule from the oil swarm, grown up.
"""

from dataclasses import dataclass
from typing import Optional
from core.registry import Signal, SignalDirection, TemporalLayer


@dataclass
class ConfidenceResult:
    score:              float
    band:               tuple[float, float]  # (low, high) uncertainty range
    meets_threshold:    bool
    verdict:            SignalDirection
    limiting_factor:    str                  # what's dragging confidence down
    alignment_score:    float                # how consistent signals are across layers
    signal_count:       int
    abstain_reason:     Optional[str] = None # set when meets_threshold is False


# Source credibility weights — how much to trust each agent type
# Modules can override these with domain-specific values
DEFAULT_CREDIBILITY = {
    "inventory_agent":    0.85,  # hard data — highest trust
    "weather_agent":      0.80,  # model-based but well-validated
    "geopolitical_agent": 0.70,  # high signal, high noise
    "shipping_agent":     0.82,  # good leading indicator
    "positioning_agent":  0.75,  # COT data — reliable but lagging
    "narrative_agent":    0.60,  # useful but lowest raw credibility
    "structural_agent":   0.72,  # good for T3, less useful for T1
    "fallback":           0.45,  # generic web agent — low trust
}


class ConfidenceEngine:
    """
    Scores aggregated signals into a single confidence result.
    The abstain rule: if score < threshold, output "insufficient signal",
    not a low-confidence guess.
    """

    def __init__(self, credibility_map: Optional[dict] = None):
        self.credibility = credibility_map or DEFAULT_CREDIBILITY

    def score(
        self,
        signals:          list[Signal],
        threshold:        float,
        alignment_score:  float = 0.0,
    ) -> ConfidenceResult:
        """
        Score a list of signals into a single confidence result.
        Applies source credibility weighting and direction consistency checks.
        """
        if not signals:
            return ConfidenceResult(
                score=0.0,
                band=(0.0, 0.0),
                meets_threshold=False,
                verdict=SignalDirection.UNKNOWN,
                limiting_factor="no signals received",
                alignment_score=0.0,
                signal_count=0,
                abstain_reason="No agent signals were produced. Cannot form a view.",
            )

        # Filter out UNKNOWN direction signals for scoring
        scoreable = [s for s in signals
                     if s.direction in (SignalDirection.BULLISH, SignalDirection.BEARISH)]

        if not scoreable:
            return ConfidenceResult(
                score=0.0,
                band=(0.0, 0.0),
                meets_threshold=False,
                verdict=SignalDirection.NEUTRAL,
                limiting_factor="all agents returned UNKNOWN — data insufficient",
                alignment_score=0.0,
                signal_count=len(signals),
                abstain_reason="All agents returned UNKNOWN direction. Data is too thin to form a view.",
            )

        # Weighted ensemble — credibility × confidence per signal
        total_weight = 0.0
        weighted_sum = 0.0
        direction_weights = {SignalDirection.BULLISH: 0.0, SignalDirection.BEARISH: 0.0}

        for s in scoreable:
            cred = self.credibility.get(s.agent_id, self.credibility["fallback"])
            weight = cred * s.confidence
            weighted_sum += s.confidence * weight
            total_weight += weight
            direction_weights[s.direction] = direction_weights.get(s.direction, 0.0) + weight

        raw_score = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Apply alignment bonus/penalty
        # All layers agree → +5% confidence, total disagreement → -10%
        alignment_adjustment = (alignment_score - 0.5) * 0.1
        final_score = min(0.98, max(0.0, raw_score + alignment_adjustment))

        # Determine verdict by weighted direction
        if direction_weights[SignalDirection.BULLISH] > direction_weights[SignalDirection.BEARISH]:
            verdict = SignalDirection.BULLISH
        elif direction_weights[SignalDirection.BEARISH] > direction_weights[SignalDirection.BULLISH]:
            verdict = SignalDirection.BEARISH
        else:
            verdict = SignalDirection.NEUTRAL

        # Confidence band — wider when signals conflict or are few
        band_width = max(0.04, 0.15 - (len(scoreable) * 0.015) - (alignment_score * 0.05))
        band = (
            round(max(0.0, final_score - band_width), 3),
            round(min(1.0, final_score + band_width), 3),
        )

        # Find limiting factor — what's dragging confidence down
        limiting = self._find_limiting_factor(scoreable, final_score)

        # Abstain if below threshold
        abstain_reason = None
        if final_score < threshold:
            abstain_reason = (
                f"Confidence {final_score:.2f} is below required threshold {threshold}. "
                f"Limiting factor: {limiting}. Do not act on this."
            )

        return ConfidenceResult(
            score=round(final_score, 3),
            band=band,
            meets_threshold=final_score >= threshold,
            verdict=verdict,
            limiting_factor=limiting,
            alignment_score=round(alignment_score, 3),
            signal_count=len(signals),
            abstain_reason=abstain_reason,
        )

    def _find_limiting_factor(self, signals: list[Signal], score: float) -> str:
        """Identify what's pulling confidence down."""
        if not signals:
            return "no signals"

        # Find the weakest signal
        weakest = min(signals, key=lambda s: s.confidence)

        # Check for high-credibility agent with low confidence
        high_cred_low_conf = [
            s for s in signals
            if self.credibility.get(s.agent_id, 0.5) > 0.75 and s.confidence < 0.5
        ]
        if high_cred_low_conf:
            names = ", ".join(s.agent_id for s in high_cred_low_conf)
            return f"high-credibility agents uncertain: {names}"

        # Check for direction conflict
        directions = {s.direction for s in signals}
        if SignalDirection.BULLISH in directions and SignalDirection.BEARISH in directions:
            return "conflicting directions across agents"

        # Default to weakest agent
        if weakest.confidence < score - 0.1:
            return f"{weakest.agent_id} low confidence ({weakest.confidence:.2f})"

        return "ensemble variance — signals agree but each has moderate confidence"

    def format_result(self, result: ConfidenceResult) -> dict:
        """Format for Layer 4 output."""
        return {
            "score":           result.score,
            "band":            f"{result.band[0]:.2f}–{result.band[1]:.2f}",
            "verdict":         result.verdict.value,
            "meets_threshold": result.meets_threshold,
            "alignment":       result.alignment_score,
            "signal_count":    result.signal_count,
            "limiting_factor": result.limiting_factor,
            **({"abstain_reason": result.abstain_reason} if result.abstain_reason else {}),
        }
