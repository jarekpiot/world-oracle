"""
Signal Store Tests (Async)
Tests persistence, history, outcomes, and track record.
Run: python -m pytest tests/test_signal_store.py -v
"""

import os
import pytest
import pytest_asyncio

# Force SQLite for tests
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_oracle.db"

from db.signal_store import SignalStore


@pytest_asyncio.fixture
async def store():
    """Fresh async store for each test."""
    s = SignalStore()
    await s.ensure_tables()
    await s.clear()
    yield s
    await s.clear()


class TestSignalStore:

    @pytest.mark.asyncio
    async def test_log_and_retrieve(self, store):
        response = {
            "status": "ORACLE_RESPONSE",
            "view": {"direction": "bullish", "confidence": 0.72},
        }
        call_id = await store.log_call("Will oil rise?", "commodity.energy.crude_oil", response)
        assert call_id >= 1

        call = await store.get_call(call_id)
        assert call is not None
        assert call["query"] == "Will oil rise?"
        assert call["domain"] == "commodity.energy.crude_oil"
        assert call["status"] == "ORACLE_RESPONSE"
        assert call["direction"] == "bullish"
        assert call["confidence"] == 0.72

    @pytest.mark.asyncio
    async def test_log_abstain(self, store):
        response = {
            "status": "INSUFFICIENT_SIGNAL",
            "confidence": 0.35,
        }
        call_id = await store.log_call("Will unobtanium rise?", "commodity.exotic", response)
        call = await store.get_call(call_id)
        assert call["status"] == "INSUFFICIENT_SIGNAL"
        assert call["direction"] is None

    @pytest.mark.asyncio
    async def test_history_returns_all(self, store):
        await store.log_call("q1", "d1", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        await store.log_call("q2", "d2", {"status": "ORACLE_RESPONSE", "view": {"direction": "bearish", "confidence": 0.6}})
        await store.log_call("q3", "d3", {"status": "INSUFFICIENT_SIGNAL", "confidence": 0.3})

        history = await store.get_history(limit=10)
        assert len(history) == 3
        queries = {h["query"] for h in history}
        assert queries == {"q1", "q2", "q3"}

    @pytest.mark.asyncio
    async def test_history_filters_by_domain(self, store):
        await store.log_call("q1", "commodity.energy.crude_oil", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        await store.log_call("q2", "fx.major.eurusd", {"status": "ORACLE_RESPONSE", "view": {"direction": "bearish", "confidence": 0.6}})

        history = await store.get_history(domain="commodity")
        assert len(history) == 1
        assert history[0]["domain"] == "commodity.energy.crude_oil"

    @pytest.mark.asyncio
    async def test_record_outcome(self, store):
        call_id = await store.log_call("q1", "d1", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        success = await store.record_outcome(call_id, "correct", "Price rose 5% in 4 weeks")
        assert success is True

        call = await store.get_call(call_id)
        assert call["outcome"] == "correct"
        assert call["notes"] == "Price rose 5% in 4 weeks"
        assert call["outcome_at"] is not None

    @pytest.mark.asyncio
    async def test_track_record(self, store):
        r = {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}}
        id1 = await store.log_call("q1", "d1", r)
        id2 = await store.log_call("q2", "d1", r)
        await store.log_call("q3", "d1", {"status": "INSUFFICIENT_SIGNAL", "confidence": 0.3})

        await store.record_outcome(id1, "correct")
        await store.record_outcome(id2, "incorrect")

        record = await store.get_track_record()
        assert record["total_calls"] == 3
        assert record["responded"] == 2
        assert record["abstained"] == 1
        assert record["scored"] == 2
        assert record["win_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_get_nonexistent_call(self, store):
        assert await store.get_call(9999) is None

    @pytest.mark.asyncio
    async def test_record_outcome_nonexistent(self, store):
        assert await store.record_outcome(9999, "correct") is False

    @pytest.mark.asyncio
    async def test_clear(self, store):
        await store.log_call("q1", "d1", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        await store.clear()
        assert await store.get_history() == []
