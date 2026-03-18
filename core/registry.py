"""
World Oracle — Module Registry
The contract every asset class module must implement.
Build this right and every future module is just a new folder dropped in.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ─── Enums ────────────────────────────────────────────────────────────────────

class QueryType(Enum):
    FACTUAL     = "factual"      # what is the current state?
    PREDICTIVE  = "predictive"   # where is this going?
    CAUSAL      = "causal"       # why is this happening?
    COMPARATIVE = "comparative"  # which is stronger/weaker?


class TemporalLayer(Enum):
    """
    The world breathes at four frequencies.
    Every signal belongs to exactly one layer.
    """
    T0 = "realtime"    # seconds to minutes  — heartbeat
    T1 = "tactical"    # hours to days       — quick breath
    T2 = "strategic"   # weeks to months     — regular breath
    T3 = "structural"  # months to years     — slow breath


class SignalDirection(Enum):
    BULLISH  = "bullish"
    BEARISH  = "bearish"
    NEUTRAL  = "neutral"
    UNKNOWN  = "unknown"   # honest — used when data is insufficient


# ─── Core Data Structures ─────────────────────────────────────────────────────

@dataclass
class Signal:
    """
    A single piece of evidence from one agent.
    Every signal must declare when it was born and what would kill it.
    """
    agent_id:        str
    source:          str
    value:           Any                    # raw agent output
    direction:       SignalDirection
    confidence:      float                  # 0.0 -> 1.0
    temporal_layer:  TemporalLayer
    generated_at:    str                    # ISO timestamp
    valid_horizon:   str                    # "2 weeks", "3 months"
    decay_triggers:  list[str]             # events that kill this signal
    domain_path:     str                    # "commodity.energy.crude_oil"
    reasoning:       str = ""              # why this agent reached this view
    raw_data:        Optional[dict] = None  # source data, for audit


@dataclass
class DecomposedQuery:
    """
    Layer 1 output. The structured query plan the orchestrator produces
    from raw natural language. Routes everything that follows.
    """
    raw:                  str
    query_type:           QueryType
    domain_path:          str            # "commodity.energy.crude_oil"
    temporal_layer:       TemporalLayer
    confidence_threshold: float          # minimum acceptable confidence
    sub_tasks:            list[dict]     # DAG nodes — parallel where possible
    reasoning:            str = ""       # why L1 decomposed it this way


@dataclass
class ModuleResponse:
    """
    What every module returns after handling a query.
    Feeds directly into Layer 3 aggregation.
    """
    module_id:        str
    domain_path:      str
    signals:          list[Signal]
    synthesised_view: SignalDirection
    confidence:       float
    reasoning_trace:  dict              # T3 -> T2 -> T1 -> T0 chain
    invalidators:     list[str]         # what would kill this thesis
    sources:          list[dict]        # [{agent, feed, timestamp}]
    temporal_layer:   TemporalLayer


@dataclass
class DataFeed:
    """Metadata about a data feed a module owns."""
    id:              str
    name:            str
    url:             str
    refresh_rate:    str    # "15min", "daily", "weekly"
    temporal_layer:  TemporalLayer
    is_free:         bool = True
    last_updated:    Optional[str] = None


# ─── Module Contract ──────────────────────────────────────────────────────────

class OracleModule(ABC):
    """
    Every asset class implements this contract.
    Register once. The oracle discovers at runtime.
    Adding FX, Crypto, Equities = new folder, same interface, core untouched.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique module identifier. e.g. 'commodities.energy'"""
        ...

    @property
    @abstractmethod
    def domain_prefix(self) -> str:
        """Routing key. e.g. 'commodity', 'fx', 'crypto'"""
        ...

    @property
    @abstractmethod
    def query_types(self) -> list[QueryType]:
        """What question types this module can handle."""
        ...

    @property
    @abstractmethod
    def temporal_layers(self) -> list[TemporalLayer]:
        """Which temporal layers this module covers."""
        ...

    @property
    @abstractmethod
    def confidence_range(self) -> tuple[float, float]:
        """Honest min/max confidence this module can produce."""
        ...

    @property
    @abstractmethod
    def feeds(self) -> list[DataFeed]:
        """Data feeds this module owns."""
        ...

    @abstractmethod
    async def handle(self, query: DecomposedQuery) -> ModuleResponse:
        """
        Core execution. Receive decomposed query, run agent pool, return signals.
        This is where the work happens.
        """
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """
        Are all feeds live? What is the data freshness?
        Returns {feed_id: {status, last_updated, latency_ms}}
        """
        ...

    @abstractmethod
    async def decay_check(self, signal: Signal) -> bool:
        """
        Has this signal's decay trigger fired?
        Returns True if signal is still valid, False if it has decayed.
        """
        ...


# ─── Module Registry ──────────────────────────────────────────────────────────

class ModuleRegistry:
    """
    The plug-in rail.
    Modules register themselves. Orchestrator resolves by domain path.
    New asset class = register a new module. Core never changes.
    """

    def __init__(self):
        self._modules: dict[str, OracleModule] = {}
        self._fallback: Optional[OracleModule] = None

    def register(self, module: OracleModule, is_fallback: bool = False):
        if is_fallback:
            self._fallback = module
            print(f"[Registry] Fallback registered: {module.id}")
        else:
            self._modules[module.domain_prefix] = module
            print(f"[Registry] Module registered: {module.id} -> prefix '{module.domain_prefix}'")

    def resolve(self, domain_path: str) -> Optional[OracleModule]:
        """
        Resolve a domain path to the right module.
        'commodity.energy.crude_oil' -> CommoditiesModule
        Unknown domain -> fallback module (low confidence floor)
        """
        prefix = domain_path.split(".")[0]
        module = self._modules.get(prefix)
        if not module:
            if self._fallback:
                print(f"[Registry] No module for '{prefix}' — using fallback")
                return self._fallback
            print(f"[Registry] WARNING: No module or fallback for '{prefix}'")
            return None
        return module

    def list_modules(self) -> list[dict]:
        return [
            {
                "id": m.id,
                "prefix": m.domain_prefix,
                "query_types": [q.value for q in m.query_types],
                "temporal_layers": [t.value for t in m.temporal_layers],
                "confidence_range": m.confidence_range,
            }
            for m in self._modules.values()
        ]

    def is_healthy(self) -> bool:
        return len(self._modules) > 0
