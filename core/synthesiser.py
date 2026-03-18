"""
World Oracle — Layer 3: Evidence Aggregation & Conflict Resolution
The hardest layer. Receives raw agent signals, resolves conflicts, produces a view.

Steps:
1. Temporal alignment — separate signals by layer, don't conflate horizons
2. Source credibility weighting
3. Claim graph — map supporting vs contradicting evidence
4. Devil's Advocate — surface the strongest counter-case
5. Confidence synthesis — weighted ensemble → single score
"""

import json
from typing import Optional
import anthropic

from core.registry import Signal, ModuleResponse, SignalDirection, TemporalLayer
from core.temporal_engine import TemporalEngine
from core.confidence_engine import ConfidenceEngine, ConfidenceResult


SYNTHESIS_PROMPT = """You are the synthesis layer of the World Oracle.

You receive signals from multiple specialist agents, each covering a different
aspect of the world's breathing cycle.

Your job:
1. Identify the dominant view across all signals
2. Note genuine conflicts (same time horizon, opposite direction)
3. Surface the 2-3 strongest reasons this view could be WRONG (Devil's Advocate)
4. Produce invalidators — specific events that would kill this thesis

Return ONLY valid JSON:
{
  "synthesised_view": "bullish|bearish|neutral",
  "dominant_thesis": "one sentence summary of the view",
  "key_supporting_signals": ["agent: reason", "agent: reason"],
  "conflicts_found": ["description of any genuine conflicts"],
  "devils_advocate": "strongest case AGAINST the dominant view",
  "invalidators": [
    "specific event or data point that would kill this thesis",
    "specific event or data point that would kill this thesis",
    "specific event or data point that would kill this thesis"
  ],
  "time_horizon": "T2 — 4 to 8 weeks",
  "reasoning": "how you weighed the signals"
}

CRITICAL RULES:
- A T1 bearish signal and T2 bullish signal are NOT a conflict — different horizons
- Only flag conflict when same layer, same domain, opposite direction
- The oracle must be willing to output "neutral" if signals genuinely cancel
- Invalidators must be SPECIFIC — not "market conditions change" but "OPEC announces
  output increase of >500k bpd" or "China PMI falls below 48"
- If data is too thin to form a view, say so in reasoning"""


class Synthesiser:
    """
    Layer 3 — Evidence Aggregation.
    Takes all agent signals and resolves them into a single coherent view.
    """

    def __init__(self, client: anthropic.AsyncAnthropic):
        self.client = client
        self.temporal = TemporalEngine()
        self.confidence = ConfidenceEngine()

    async def synthesise(
        self,
        signals:    list[Signal],
        query_raw:  str,
        threshold:  float,
        domain:     str,
    ) -> tuple[dict, ConfidenceResult]:
        """
        Main synthesis pipeline.
        Returns (synthesis_result, confidence_result)
        """

        if not signals:
            empty_conf = self.confidence.score([], threshold)
            return {
                "synthesised_view": "unknown",
                "dominant_thesis": "No signals — cannot form a view.",
                "invalidators": [],
                "devils_advocate": "N/A",
                "conflicts_found": [],
                "key_supporting_signals": [],
                "time_horizon": "unknown",
                "reasoning": "No agent signals were received.",
            }, empty_conf

        # Step 1: Temporal alignment — group by layer
        layer_summary = self.temporal.layer_summary(signals)
        alignment = self.temporal.alignment_score(signals)
        reasoning_trace = self.temporal.build_reasoning_trace(signals)
        decay_risks = self.temporal.decay_summary(signals)

        # Step 2: Score confidence before synthesis
        confidence_result = self.confidence.score(signals, threshold, alignment)

        # Step 3: Build signal context for LLM synthesis
        signal_context = self._build_signal_context(signals, layer_summary, decay_risks)

        # Step 4: LLM synthesis (one call — no reasoning drift from multiple LLMs)
        synthesis = await self._llm_synthesise(query_raw, signal_context, domain)

        # Attach the temporal trace
        synthesis["reasoning_trace"] = reasoning_trace
        synthesis["alignment_score"] = alignment
        synthesis["decay_risks"] = list(decay_risks.keys())[:5]

        return synthesis, confidence_result

    def _build_signal_context(
        self,
        signals:       list[Signal],
        layer_summary: dict,
        decay_risks:   dict,
    ) -> str:
        """Format signals into a clear context block for the synthesis LLM."""
        lines = ["AGENT SIGNALS:\n"]

        for s in signals:
            lines.append(
                f"[{s.agent_id}] Layer:{s.temporal_layer.value} | "
                f"Direction:{s.direction.value} | Confidence:{s.confidence:.2f}\n"
                f"  Source: {s.source}\n"
                f"  Reasoning: {s.reasoning[:200] if s.reasoning else 'not provided'}\n"
                f"  Decay triggers: {', '.join(s.decay_triggers[:3]) if s.decay_triggers else 'none specified'}\n"
            )

        lines.append("\nLAYER COVERAGE:")
        for layer, layer_signals in layer_summary.items():
            if layer_signals:
                dirs = [ls["direction"] for ls in layer_signals]
                confs = [ls["confidence"] for ls in layer_signals]
                avg = sum(confs) / len(confs) if confs else 0
                lines.append(f"  {layer}: {dirs} (avg confidence {avg:.2f})")
            else:
                lines.append(f"  {layer}: NO COVERAGE")

        if decay_risks:
            lines.append("\nTOP DECAY RISKS (events that would invalidate most signals):")
            for trigger, count in list(decay_risks.items())[:5]:
                lines.append(f"  • {trigger} (affects {count} signals)")

        return "\n".join(lines)

    async def _llm_synthesise(
        self,
        query:          str,
        signal_context: str,
        domain:         str,
    ) -> dict:
        """Single LLM call for synthesis — no multiple LLM opinions colliding."""
        user_content = (
            f"Domain: {domain}\n"
            f"Query: {query}\n\n"
            f"{signal_context}"
        )

        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=SYNTHESIS_PROMPT,
            messages=[{"role": "user", "content": user_content}]
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences (Haiku often wraps JSON in ```json)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {
                "synthesised_view": "unknown",
                "dominant_thesis": "Synthesis parse error",
                "invalidators": [],
                "devils_advocate": raw[:200],
                "conflicts_found": [],
                "key_supporting_signals": [],
                "time_horizon": "unknown",
                "reasoning": f"Parse error on synthesis response: {raw[:100]}",
            }
