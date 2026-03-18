"""
World Oracle — Layer 4: Answer + Output
The oracle's final word. Structured, honest, with full provenance.

Every response includes:
- The view (with honest uncertainty)
- Confidence band (not false precision)
- Reasoning trace (T3 → T2 → T1 → T0)
- Invalidators (what would make this wrong)
- Sources with timestamps
- Or: a clean abstain with the reason why
"""

from datetime import datetime, timezone
from core.registry import SignalDirection
from core.confidence_engine import ConfidenceResult


def format_oracle_response(
    query:       str,
    domain:      str,
    synthesis:   dict,
    confidence:  ConfidenceResult,
    sources:     list[dict],
) -> dict:
    """
    Format the final oracle response.
    If confidence threshold not met → ABSTAIN, not a low-confidence guess.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # ABSTAIN — the oracle says "don't act" rather than fabricate
    if not confidence.meets_threshold:
        return {
            "status":      "INSUFFICIENT_SIGNAL",
            "timestamp":   timestamp,
            "query":       query,
            "domain":      domain,
            "confidence":  confidence.score,
            "reason":      confidence.abstain_reason,
            "limiting":    confidence.limiting_factor,
            "oracle_says": "Insufficient signal — do not act on this query.",
            "what_to_do":  "Wait for one of these signals to strengthen: "
                           + (synthesis.get("devils_advocate", "unclear")[:200]),
        }

    # RESPONSE — the oracle has something to say
    view = synthesis.get("synthesised_view", "neutral")
    direction_map = {
        "bullish": SignalDirection.BULLISH,
        "bearish": SignalDirection.BEARISH,
        "neutral": SignalDirection.NEUTRAL,
    }

    return {
        "status":           "ORACLE_RESPONSE",
        "timestamp":        timestamp,
        "query":            query,
        "domain":           domain,

        "view": {
            "direction":     view,
            "thesis":        synthesis.get("dominant_thesis", ""),
            "time_horizon":  synthesis.get("time_horizon", ""),
            "confidence":    confidence.score,
            "band":          f"{confidence.band[0]:.2f}–{confidence.band[1]:.2f}",
            "alignment":     confidence.alignment_score,
        },

        "reasoning_trace":  synthesis.get("reasoning_trace", {}),

        "risk": {
            "invalidators":     synthesis.get("invalidators", []),
            "devils_advocate":  synthesis.get("devils_advocate", ""),
            "decay_risks":      synthesis.get("decay_risks", []),
            "conflicts":        synthesis.get("conflicts_found", []),
        },

        "evidence": {
            "signal_count":         confidence.signal_count,
            "supporting_signals":   synthesis.get("key_supporting_signals", []),
            "sources":              sources,
        },

        "meta": {
            "limiting_factor":  confidence.limiting_factor,
            "synthesis_notes":  synthesis.get("reasoning", "")[:300],
        },
    }


def print_oracle_response(response: dict) -> None:
    """Pretty-print an oracle response to terminal."""
    print("\n" + "═" * 60)

    if response["status"] == "INSUFFICIENT_SIGNAL":
        print(f"  ORACLE: ABSTAINING")
        print(f"  Query:  {response['query'][:70]}")
        print(f"  Reason: {response['reason'][:120]}")
        print("═" * 60 + "\n")
        return

    v = response["view"]
    direction_symbols = {"bullish": "▲", "bearish": "▼", "neutral": "━"}
    symbol = direction_symbols.get(v["direction"], "?")

    print(f"  ORACLE RESPONSE  {symbol} {v['direction'].upper()}")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"  Query:      {response['query'][:65]}")
    print(f"  Domain:     {response['domain']}")
    print(f"  Thesis:     {v['thesis'][:70]}")
    print(f"  Horizon:    {v['time_horizon']}")
    print(f"  Confidence: {v['confidence']:.2f}  [{v['band']}]")
    print(f"  Alignment:  {v['alignment']:.2f}")

    print(f"\n  REASONING TRACE (T3 → T2 → T1 → T0):")
    for layer, data in response.get("reasoning_trace", {}).items():
        status = data.get("status", "—")
        conf = f"  {data['confidence']:.2f}" if data.get("confidence") else ""
        agents = ", ".join(data.get("agents", []))
        print(f"    {layer}: {status}{conf}  [{agents}]")

    print(f"\n  INVALIDATORS (what would kill this thesis):")
    for inv in response["risk"].get("invalidators", []):
        print(f"    • {inv}")

    print(f"\n  DEVIL'S ADVOCATE:")
    print(f"    {response['risk'].get('devils_advocate', '')[:120]}")

    print(f"\n  SIGNALS: {response['evidence']['signal_count']} received")
    print("═" * 60 + "\n")
