"""
World Oracle — Main Entry Point
Wires all four layers together.
The spine. Everything else plugs into this.

Usage:
  python main.py
  python main.py --query "Will crude oil prices rise over the next 6 weeks?"
"""

import asyncio
import json
import argparse
import os
import sys

# Fix Windows console encoding — allow Unicode box-drawing characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import anthropic

from core.registry import ModuleRegistry
from core.query_engine import QueryEngine
from core.synthesiser import Synthesiser
from output.formatter import format_oracle_response, print_oracle_response


async def run_oracle(query: str, verbose: bool = True) -> dict:
    """
    Run the World Oracle on a single query.
    Returns structured response dict.
    """
    client = anthropic.AsyncAnthropic()

    # Initialise core engines
    registry    = ModuleRegistry()
    query_engine = QueryEngine(client)
    synthesiser  = Synthesiser(client)

    # ── Register modules ───────────────────────────────────────────────────
    # Commodities seed module — the first plug
    try:
        from modules.commodities import CommoditiesModule
        registry.register(CommoditiesModule(client))
    except ImportError:
        print("[Main] Commodities module not yet built — using fallback only")

    # FX module — second plug
    try:
        from modules.fx import FXModule
        registry.register(FXModule(client))
    except ImportError:
        print("[Main] FX module not yet built — skipping")

    # Crypto module — third plug
    try:
        from modules.crypto import CryptoModule
        registry.register(CryptoModule(client))
    except ImportError:
        print("[Main] Crypto module not yet built — skipping")

    if verbose:
        print(f"\n[Oracle] Registered modules: {[m['id'] for m in registry.list_modules()]}")

    # ── Layer 1: Query Understanding ───────────────────────────────────────
    if verbose:
        print(f"[Oracle] Decomposing query...")

    decomposed = await query_engine.decompose(query)

    if verbose:
        query_engine.log_decomposition(decomposed)

    # ── Layer 2: Route to Module ───────────────────────────────────────────
    module = registry.resolve(decomposed.domain_path)

    if not module:
        return {
            "status":      "NO_MODULE",
            "query":       query,
            "domain":      decomposed.domain_path,
            "oracle_says": f"No module registered for domain '{decomposed.domain_path}'. "
                           f"Build the module and register it in main.py.",
        }

    if verbose:
        print(f"[Oracle] Routing to module: {module.id}")

    # ── Module Execution (Agent Pool) ──────────────────────────────────────
    module_response = await module.handle(decomposed)

    if verbose:
        print(f"[Oracle] Module returned {len(module_response.signals)} signals")

    # ── Layer 3: Evidence Aggregation ──────────────────────────────────────
    if verbose:
        print(f"[Oracle] Synthesising signals...")

    synthesis, confidence = await synthesiser.synthesise(
        signals=module_response.signals,
        query_raw=query,
        threshold=decomposed.confidence_threshold,
        domain=decomposed.domain_path,
    )

    # ── Layer 4: Format Output ─────────────────────────────────────────────
    result = format_oracle_response(
        query=query,
        domain=decomposed.domain_path,
        synthesis=synthesis,
        confidence=confidence,
        sources=module_response.sources,
    )

    if verbose:
        print_oracle_response(result)

    return result


async def health_check():
    """Check all registered modules and their data feeds."""
    client = anthropic.AsyncAnthropic()
    registry = ModuleRegistry()

    try:
        from modules.commodities import CommoditiesModule
        registry.register(CommoditiesModule(client))
    except ImportError:
        print("Commodities module not built yet")

    try:
        from modules.fx import FXModule
        registry.register(FXModule(client))
    except ImportError:
        print("FX module not built yet")

    try:
        from modules.crypto import CryptoModule
        registry.register(CryptoModule(client))
    except ImportError:
        print("Crypto module not built yet")

    print("\n[Health Check] ─────────────────────────────")
    for module_info in registry.list_modules():
        print(f"  Module: {module_info['id']}")
        print(f"  Prefix: {module_info['prefix']}")
        print(f"  Layers: {module_info['temporal_layers']}")
        print(f"  Conf range: {module_info['confidence_range']}")
    print("─────────────────────────────────────────────\n")


def main():
    parser = argparse.ArgumentParser(description="World Oracle")
    parser.add_argument("--query", type=str,
                        default="Will crude oil prices rise over the next 6 weeks?",
                        help="Natural language query for the oracle")
    parser.add_argument("--health", action="store_true",
                        help="Run health check on all modules")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted print")
    args = parser.parse_args()

    if args.health:
        asyncio.run(health_check())
        return

    result = asyncio.run(run_oracle(args.query, verbose=not args.json))

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
