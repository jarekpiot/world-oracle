"""
World Oracle — FastAPI Server
Exposes the oracle over HTTP. Async throughout.

Endpoints:
  POST /api/query     — run a query through the oracle
  GET  /api/health    — module registry + feed health
  GET  /api/modules   — registered modules and their capabilities
  GET  /api/history   — past oracle calls with outcomes

Rate limit: 60 requests/minute default.
"""

import asyncio
import time
import logging
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.registry import ModuleRegistry
from core.query_engine import QueryEngine
from core.synthesiser import Synthesiser
from core.feed_monitor import FeedMonitor, run_periodic_health_check
from output.formatter import format_oracle_response
from db.signal_store import SignalStore


logger = logging.getLogger("world_oracle.api")

# ─── Rate Limiter ────────────────────────────────────────────────────────────

RATE_LIMIT_PER_MINUTE = 60


class RateLimiter:
    """Simple in-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = RATE_LIMIT_PER_MINUTE, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: deque[float] = deque()

    def allow(self) -> bool:
        now = time.time()
        # Purge old entries
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()
        if len(self.requests) >= self.max_requests:
            return False
        self.requests.append(now)
        return True

    @property
    def remaining(self) -> int:
        now = time.time()
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()
        return max(0, self.max_requests - len(self.requests))


# ─── Shared State ────────────────────────────────────────────────────────────

rate_limiter = RateLimiter()
signal_store = SignalStore()
registry = ModuleRegistry()
feed_monitor: Optional[FeedMonitor] = None
client: Optional[anthropic.AsyncAnthropic] = None
query_engine: Optional[QueryEngine] = None
synthesiser: Optional[Synthesiser] = None


def _init_oracle():
    """Initialise the oracle components and register modules."""
    global client, query_engine, synthesiser, feed_monitor

    client = anthropic.AsyncAnthropic()
    query_engine = QueryEngine(client)
    synthesiser = Synthesiser(client)
    feed_monitor = FeedMonitor(registry)

    # Register modules
    try:
        from modules.commodities import CommoditiesModule
        registry.register(CommoditiesModule(client))
    except ImportError:
        logger.warning("Commodities module not available")

    try:
        from modules.fx import FXModule
        registry.register(FXModule(client))
    except ImportError:
        logger.warning("FX module not available")

    try:
        from modules.crypto import CryptoModule
        registry.register(CryptoModule(client))
    except ImportError:
        logger.warning("Crypto module not available")


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    _init_oracle()
    logger.info("Oracle initialised — %d modules registered", len(registry.list_modules()))

    # Run initial health check
    if feed_monitor:
        await feed_monitor.check_all_feeds()
        logger.info("Initial feed health check complete")

    # Start periodic health check in background
    health_task = asyncio.create_task(
        run_periodic_health_check(registry, interval_seconds=900)
    )

    yield

    # Shutdown
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="World Oracle",
    description="AI system that reads the world's breathing cycles across markets.",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Request / Response Models ───────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=1000, description="Natural language query")


class OutcomeRequest(BaseModel):
    outcome: str = Field(..., pattern="^(correct|incorrect|partial|inconclusive)$")
    notes: str = Field(default="", max_length=500)


# ─── Middleware ───────────────────────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limit all requests."""
    if not rate_limiter.allow():
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": f"Max {RATE_LIMIT_PER_MINUTE} requests per minute",
                "retry_after_seconds": 60,
            },
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(rate_limiter.remaining)
    return response


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/api/query")
async def oracle_query(req: QueryRequest):
    """
    Run a query through the oracle.
    Returns 200 with status=INSUFFICIENT_SIGNAL for abstain cases (not 4xx).
    Logs every call to the signal store.
    """
    # Layer 1: Decompose
    decomposed = await query_engine.decompose(req.query)

    # Layer 2: Route to module
    module = registry.resolve(decomposed.domain_path)

    if not module:
        result = {
            "status": "NO_MODULE",
            "query": req.query,
            "domain": decomposed.domain_path,
            "oracle_says": f"No module registered for domain '{decomposed.domain_path}'.",
        }
        signal_store.log_call(req.query, decomposed.domain_path, result)
        return result

    # Module execution
    module_response = await module.handle(decomposed)

    # Layer 3: Synthesise
    synthesis, confidence = await synthesiser.synthesise(
        signals=module_response.signals,
        query_raw=req.query,
        threshold=decomposed.confidence_threshold,
        domain=decomposed.domain_path,
    )

    # Layer 4: Format
    result = format_oracle_response(
        query=req.query,
        domain=decomposed.domain_path,
        synthesis=synthesis,
        confidence=confidence,
        sources=module_response.sources,
    )

    # Log to signal store
    call_id = signal_store.log_call(req.query, decomposed.domain_path, result)
    result["call_id"] = call_id

    return result


@app.get("/api/health")
async def health_check():
    """Module registry status + feed health."""
    feed_health = {}
    if feed_monitor:
        feed_health = feed_monitor.last_check or await feed_monitor.check_all_feeds()

    return {
        "status": "ok" if registry.is_healthy() else "no_modules",
        "modules_registered": len(registry.list_modules()),
        "feed_health": feed_health,
        "feed_summary": feed_monitor.summary() if feed_monitor else {},
        "last_health_check": feed_monitor.last_check_at if feed_monitor else None,
    }


@app.get("/api/modules")
async def list_modules():
    """Registered modules, their temporal coverage, confidence ranges."""
    return {
        "modules": registry.list_modules(),
        "count": len(registry.list_modules()),
    }


@app.get("/api/history")
async def get_history(limit: int = 50, domain: Optional[str] = None):
    """Last N oracle calls with outcomes."""
    history = signal_store.get_history(limit=min(limit, 200), domain=domain)
    track_record = signal_store.get_track_record(domain=domain)
    return {
        "calls": history,
        "track_record": track_record,
    }


@app.get("/api/history/{call_id}")
async def get_call(call_id: int):
    """Get a single oracle call by ID, including full response."""
    call = signal_store.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@app.post("/api/history/{call_id}/outcome")
async def record_outcome(call_id: int, req: OutcomeRequest):
    """Record the market outcome for a past oracle call."""
    call = signal_store.get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    success = signal_store.record_outcome(call_id, req.outcome, req.notes)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to record outcome")

    return {"status": "recorded", "call_id": call_id, "outcome": req.outcome}
