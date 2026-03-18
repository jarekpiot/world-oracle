"""
World Oracle — Streamlit Dashboard
Four pages: Live Oracle, Signal History, Feed Health, Breathing Map.

Run: streamlit run dashboard/app.py
"""

import sys
import os
import json
import asyncio
from datetime import datetime

import streamlit as st

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.signal_store import SignalStore

# ─── Config ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="World Oracle",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_URL = os.environ.get("ORACLE_API_URL", "http://localhost:8000")

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _get_store() -> SignalStore:
    """Get or create a SignalStore instance."""
    if "store" not in st.session_state:
        st.session_state.store = SignalStore()
    return st.session_state.store


def _run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _init_oracle():
    """Initialise oracle components (cached across reruns)."""
    if "oracle_ready" not in st.session_state:
        try:
            import anthropic
            from core.registry import ModuleRegistry
            from core.query_engine import QueryEngine
            from core.synthesiser import Synthesiser
            from core.feed_monitor import FeedMonitor
            from output.formatter import format_oracle_response

            client = anthropic.AsyncAnthropic()
            registry = ModuleRegistry()
            query_engine = QueryEngine(client)
            synthesiser = Synthesiser(client)

            try:
                from modules.commodities import CommoditiesModule
                registry.register(CommoditiesModule(client))
            except ImportError:
                pass

            feed_monitor = FeedMonitor(registry)

            st.session_state.client = client
            st.session_state.registry = registry
            st.session_state.query_engine = query_engine
            st.session_state.synthesiser = synthesiser
            st.session_state.feed_monitor = feed_monitor
            st.session_state.oracle_ready = True
        except Exception as e:
            st.session_state.oracle_ready = False
            st.session_state.oracle_error = str(e)


_init_oracle()


# ─── Sidebar ─────────────────────────────────────────────────────────────────

st.sidebar.title("World Oracle")
st.sidebar.caption("Reading the world's breathing cycles")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["Live Oracle", "Signal History", "Feed Health", "Breathing Map"],
    index=0,
)

st.sidebar.divider()
st.sidebar.markdown(
    "**Temporal Layers**\n"
    "- **T3** Slow Breath (months-years)\n"
    "- **T2** Regular Breath (weeks-months)\n"
    "- **T1** Quick Breath (hours-days)\n"
    "- **T0** Heartbeat (seconds-minutes)"
)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 1: LIVE ORACLE
# ═════════════════════════════════════════════════════════════════════════════

def page_live_oracle():
    st.header("Live Oracle")
    st.caption("Ask the oracle a question about global markets")

    query = st.text_input(
        "Query",
        placeholder="Will crude oil prices rise over the next 6 weeks?",
        key="oracle_query",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        run = st.button("Ask Oracle", type="primary", use_container_width=True)

    if not run or not query:
        # Show example queries
        st.divider()
        st.subheader("Example Queries")
        examples = [
            "Will crude oil prices rise over the next 6 weeks?",
            "What is the structural outlook for copper?",
            "Is natural gas bullish or bearish this winter?",
            "Why is gold rising?",
            "Compare crude oil and natural gas outlook",
        ]
        for ex in examples:
            st.code(ex, language=None)
        return

    if not st.session_state.get("oracle_ready"):
        st.error(f"Oracle not initialised: {st.session_state.get('oracle_error', 'unknown error')}")
        return

    # Run the oracle
    with st.spinner("Oracle is reading the world's breathing..."):
        try:
            from output.formatter import format_oracle_response

            decomposed = _run_async(
                st.session_state.query_engine.decompose(query)
            )

            module = st.session_state.registry.resolve(decomposed.domain_path)

            if not module:
                st.warning(f"No module registered for domain: **{decomposed.domain_path}**")
                return

            module_response = _run_async(module.handle(decomposed))

            synthesis, confidence = _run_async(
                st.session_state.synthesiser.synthesise(
                    signals=module_response.signals,
                    query_raw=query,
                    threshold=decomposed.confidence_threshold,
                    domain=decomposed.domain_path,
                )
            )

            result = format_oracle_response(
                query=query,
                domain=decomposed.domain_path,
                synthesis=synthesis,
                confidence=confidence,
                sources=module_response.sources,
            )

            # Log to store
            store = _get_store()
            call_id = store.log_call(query, decomposed.domain_path, result)

        except Exception as e:
            st.error(f"Oracle error: {e}")
            return

    # ── Display Result ───────────────────────────────────────────────
    st.divider()

    if result["status"] == "INSUFFICIENT_SIGNAL":
        _render_abstain(result)
    else:
        _render_response(result)

    # Show raw JSON in expander
    with st.expander("Raw Oracle Response"):
        st.json(result)


def _render_abstain(result):
    """Render an ABSTAIN response — make it prominent."""
    st.error("ORACLE: ABSTAINING — Insufficient Signal")
    st.markdown(f"**Query:** {result['query']}")
    st.markdown(f"**Domain:** {result['domain']}")
    st.markdown(f"**Confidence:** {result.get('confidence', 0):.2f}")

    st.warning(f"**Reason:** {result.get('reason', 'Unknown')}")

    if result.get("what_to_do"):
        st.info(f"**What to do:** {result['what_to_do']}")

    st.caption("Abstaining is a feature, not a failure. The oracle says 'wait' when the signal is too thin.")


def _render_response(result):
    """Render a full oracle response with all layers."""
    view = result["view"]
    direction = view["direction"]

    # Direction banner
    symbols = {"bullish": "▲", "bearish": "▼", "neutral": "━"}
    colors = {"bullish": "green", "bearish": "red", "neutral": "orange"}
    symbol = symbols.get(direction, "?")
    color = colors.get(direction, "gray")

    st.markdown(
        f"### {symbol} **{direction.upper()}**",
    )

    # Key metrics in columns
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Confidence", f"{view['confidence']:.2f}")
    c2.metric("Band", view["band"])
    c3.metric("Alignment", f"{view['alignment']:.2f}")
    c4.metric("Signals", result["evidence"]["signal_count"])

    # Thesis
    st.markdown(f"**Thesis:** {view.get('thesis', '')}")
    st.markdown(f"**Horizon:** {view.get('time_horizon', '')}")
    st.markdown(f"**Domain:** {result['domain']}")

    st.divider()

    # Reasoning Trace (T3 → T0)
    st.subheader("Reasoning Trace (T3 → T0)")
    trace = result.get("reasoning_trace", {})

    layer_labels = {
        "structural": "T3 — Slow Breath",
        "strategic": "T2 — Regular Breath",
        "tactical": "T1 — Quick Breath",
        "realtime": "T0 — Heartbeat",
    }

    for layer_key in ["structural", "strategic", "tactical", "realtime"]:
        data = trace.get(layer_key, {})
        status = data.get("status", "no signal")
        conf = data.get("confidence")
        agents = ", ".join(data.get("agents", []))
        reasoning = data.get("reasoning", "")

        label = layer_labels.get(layer_key, layer_key)

        if status == "no signal":
            st.markdown(f"**{label}:** _no signal_")
        else:
            dir_symbol = symbols.get(status, "?")
            conf_str = f" ({conf:.2f})" if conf else ""
            st.markdown(f"**{label}:** {dir_symbol} {status}{conf_str}")
            if agents:
                st.caption(f"Agents: {agents}")
            if reasoning:
                with st.expander(f"{label} reasoning"):
                    st.write(reasoning)

    st.divider()

    # Risk section
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Invalidators")
        st.caption("Events that would kill this thesis")
        for inv in result["risk"].get("invalidators", []):
            st.markdown(f"- {inv}")

    with col_right:
        st.subheader("Devil's Advocate")
        st.caption("Strongest case against the dominant view")
        st.markdown(result["risk"].get("devils_advocate", "N/A"))

        if result["risk"].get("conflicts"):
            st.warning("**Conflicts detected:**")
            for c in result["risk"]["conflicts"]:
                st.markdown(f"- {c}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 2: SIGNAL HISTORY
# ═════════════════════════════════════════════════════════════════════════════

def page_signal_history():
    st.header("Signal History")
    st.caption("Past oracle calls, confidence scores, and outcomes")

    store = _get_store()

    # Filters
    col1, col2 = st.columns([2, 1])
    with col1:
        domain_filter = st.text_input("Filter by domain", placeholder="commodity.energy")
    with col2:
        limit = st.number_input("Results", min_value=5, max_value=200, value=50)

    history = store.get_history(
        limit=limit,
        domain=domain_filter if domain_filter else None,
    )

    if not history:
        st.info("No oracle calls recorded yet. Run a query from the Live Oracle page.")
        return

    # Track record summary
    track = store.get_track_record(domain=domain_filter if domain_filter else None)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Calls", track["total_calls"])
    c2.metric("Responded", track["responded"])
    c3.metric("Abstained", track["abstained"])
    c4.metric("Scored", track["scored"])
    c5.metric("Win Rate", f"{track['win_rate']:.1%}" if track["win_rate"] is not None else "N/A")

    st.divider()

    # Call list
    for call in history:
        status_icon = "🟢" if call["status"] == "ORACLE_RESPONSE" else "🟡"
        direction_str = f" → {call['direction']}" if call.get("direction") else ""
        conf_str = f" ({call['confidence']:.2f})" if call.get("confidence") else ""
        outcome_str = f" | Outcome: **{call['outcome']}**" if call.get("outcome") else ""

        with st.expander(
            f"{status_icon} {call['query'][:60]}{direction_str}{conf_str}{outcome_str}"
        ):
            st.markdown(f"**ID:** {call['id']}")
            st.markdown(f"**Domain:** {call['domain']}")
            st.markdown(f"**Status:** {call['status']}")
            st.markdown(f"**Time:** {call['timestamp']}")

            if call.get("direction"):
                st.markdown(f"**Direction:** {call['direction']}")
            if call.get("confidence"):
                st.markdown(f"**Confidence:** {call['confidence']:.3f}")
            if call.get("outcome"):
                st.markdown(f"**Outcome:** {call['outcome']}")
                st.markdown(f"**Notes:** {call.get('notes', '')}")

            # Outcome recording
            if not call.get("outcome"):
                st.markdown("---")
                st.caption("Record market outcome:")
                oc1, oc2 = st.columns(2)
                with oc1:
                    outcome = st.selectbox(
                        "Outcome",
                        ["correct", "incorrect", "partial", "inconclusive"],
                        key=f"outcome_{call['id']}",
                    )
                with oc2:
                    notes = st.text_input("Notes", key=f"notes_{call['id']}")

                if st.button("Record", key=f"record_{call['id']}"):
                    store.record_outcome(call["id"], outcome, notes)
                    st.success(f"Outcome recorded: {outcome}")
                    st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 3: FEED HEALTH
# ═════════════════════════════════════════════════════════════════════════════

def page_feed_health():
    st.header("Feed Health")
    st.caption("Live status of all data feeds across registered modules")

    if not st.session_state.get("oracle_ready"):
        st.error("Oracle not initialised")
        return

    monitor = st.session_state.feed_monitor

    if st.button("Run Health Check", type="primary"):
        with st.spinner("Checking feeds..."):
            _run_async(monitor.check_all_feeds())

    if not monitor.last_check:
        st.info("No health check has been run yet. Click the button above.")
        return

    summary = monitor.summary()

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    status_color = "green" if summary["status"] == "healthy" else "orange"
    c1.metric("Status", summary["status"].upper())
    c2.metric("Total Feeds", summary["total_feeds"])
    c3.metric("Healthy", summary["healthy"])
    c4.metric("Unhealthy", summary["unhealthy"])

    st.caption(f"Last checked: {monitor.last_check_at}")

    st.divider()

    # Per-module breakdown
    for module_id, feeds in monitor.last_check.items():
        st.subheader(f"Module: {module_id}")

        if isinstance(feeds, dict) and "status" in feeds and not any(
            isinstance(v, dict) for v in feeds.values()
        ):
            # Module-level error
            st.error(f"Module error: {feeds.get('message', feeds.get('status'))}")
            continue

        for feed_id, feed_data in feeds.items():
            if not isinstance(feed_data, dict):
                continue

            status = feed_data.get("status", "unknown")
            status_icon = {
                "ok": "🟢",
                "partial": "🟡",
                "no_api_key": "🔴",
                "not_connected": "🔴",
                "error": "🔴",
            }.get(status, "⚪")

            message = feed_data.get("message", "")
            last = feed_data.get("last_fetched")
            last_str = datetime.fromtimestamp(last).isoformat() if last else "never"

            st.markdown(f"{status_icon} **{feed_id}** — {status}")
            if message:
                st.caption(message)
            st.caption(f"Last fetched: {last_str}")

    # Warnings
    if summary.get("warnings"):
        st.divider()
        st.subheader("Warnings")
        for w in summary["warnings"]:
            st.warning(w)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 4: BREATHING MAP
# ═════════════════════════════════════════════════════════════════════════════

def page_breathing_map():
    st.header("Breathing Map")
    st.caption("Visual of T3 → T0 layers with current signal state")

    if not st.session_state.get("oracle_ready"):
        st.error("Oracle not initialised")
        return

    st.markdown("""
    The world breathes at four frequencies simultaneously.
    Each layer answers a different question about the **present** state.
    """)

    # Domain selector
    domain = st.selectbox(
        "Domain",
        [
            "commodity.energy.crude_oil",
            "commodity.energy.natural_gas",
            "commodity.metals.copper",
            "commodity.metals.gold",
            "commodity.agriculture.wheat",
        ],
    )

    if st.button("Read Breathing Cycle", type="primary"):
        with st.spinner("Reading the world's breathing..."):
            try:
                from core.registry import DecomposedQuery, QueryType, TemporalLayer

                module = st.session_state.registry.resolve(domain)
                if not module:
                    st.error(f"No module for domain: {domain}")
                    return

                query = DecomposedQuery(
                    raw=f"What is the current state of {domain}?",
                    query_type=QueryType.FACTUAL,
                    domain_path=domain,
                    temporal_layer=TemporalLayer.T2,
                    confidence_threshold=0.50,
                    sub_tasks=[],
                )

                response = _run_async(module.handle(query))
                signals = response.signals

            except Exception as e:
                st.error(f"Error: {e}")
                return

        st.divider()

        # Build the breathing map
        from core.temporal_engine import TemporalEngine
        from core.registry import TemporalLayer as TL

        engine = TemporalEngine()
        trace = engine.build_reasoning_trace(signals)
        alignment = engine.alignment_score(signals)

        # Alignment banner
        if alignment >= 0.8:
            st.success(f"**Alignment: {alignment:.2f}** — Breathing cycles converging. High conviction zone.")
        elif alignment >= 0.5:
            st.warning(f"**Alignment: {alignment:.2f}** — Mixed signals across layers. Moderate conviction.")
        else:
            st.error(f"**Alignment: {alignment:.2f}** — Layers diverging. Oracle would likely abstain.")

        st.divider()

        # Four-layer visualization
        layers = [
            ("T3 — SLOW BREATH", "structural", "months → years", "The deep rhythm"),
            ("T2 — REGULAR BREATH", "strategic", "weeks → months", "The macro cycle"),
            ("T1 — QUICK BREATH", "tactical", "hours → days", "Narrative momentum"),
            ("T0 — HEARTBEAT", "realtime", "seconds → minutes", "Price and flow"),
        ]

        symbols = {"bullish": "▲", "bearish": "▼", "neutral": "━", "no signal": "○"}
        colors_map = {"bullish": "green", "bearish": "red", "neutral": "orange"}

        for title, key, timeframe, description in layers:
            data = trace.get(key, {})
            status = data.get("status", "no signal")
            conf = data.get("confidence")
            agents = data.get("agents", [])
            reasoning = data.get("reasoning", "")

            symbol = symbols.get(status, "?")

            st.markdown(f"### {symbol} {title}")
            st.caption(f"{timeframe} — {description}")

            if status == "no signal":
                st.markdown("_No agent coverage at this layer_")
            else:
                conf_str = f"**Confidence:** {conf:.2f}" if conf else ""
                st.markdown(f"**Direction:** {status.upper()} {conf_str}")

                if agents:
                    st.markdown(f"**Agents:** {', '.join(agents)}")

                if reasoning:
                    st.markdown(f"_{reasoning[:200]}_")

            # Find signals at this layer
            layer_map = {"structural": TL.T3, "strategic": TL.T2, "tactical": TL.T1, "realtime": TL.T0}
            tl = layer_map.get(key)
            layer_signals = [s for s in signals if s.temporal_layer == tl] if tl else []

            if layer_signals:
                with st.expander(f"Signals at {title} ({len(layer_signals)})"):
                    for s in layer_signals:
                        dir_sym = symbols.get(s.direction.value, "?")
                        st.markdown(
                            f"- {dir_sym} **{s.agent_id}** — {s.direction.value} "
                            f"(conf: {s.confidence:.2f}) via {s.source}"
                        )
                        if s.reasoning:
                            st.caption(s.reasoning[:150])

            st.divider()

        # Decay risks
        decay = engine.decay_summary(signals)
        if decay:
            st.subheader("Decay Risks")
            st.caption("Events that would invalidate the most signals")
            for trigger, count in list(decay.items())[:5]:
                st.markdown(f"- **{trigger}** (affects {count} signal{'s' if count > 1 else ''})")


# ─── Router ──────────────────────────────────────────────────────────────────

pages = {
    "Live Oracle": page_live_oracle,
    "Signal History": page_signal_history,
    "Feed Health": page_feed_health,
    "Breathing Map": page_breathing_map,
}

pages[page]()
