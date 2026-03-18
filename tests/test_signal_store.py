"""
Signal Store Tests
Tests persistence, history, outcomes, and track record.
Run: python -m pytest tests/test_signal_store.py -v
"""

import os
import pytest
from db.signal_store import SignalStore


@pytest.fixture
def store(tmp_path):
    """Fresh SQLite store in a temp directory."""
    db_path = str(tmp_path / "test_oracle.db")
    s = SignalStore(db_path=db_path)
    yield s


class TestSignalStore:

    def test_log_and_retrieve(self, store):
        response = {
            "status": "ORACLE_RESPONSE",
            "view": {"direction": "bullish", "confidence": 0.72},
        }
        call_id = store.log_call("Will oil rise?", "commodity.energy.crude_oil", response)
        assert call_id >= 1

        call = store.get_call(call_id)
        assert call is not None
        assert call["query"] == "Will oil rise?"
        assert call["domain"] == "commodity.energy.crude_oil"
        assert call["status"] == "ORACLE_RESPONSE"
        assert call["direction"] == "bullish"
        assert call["confidence"] == 0.72

    def test_log_abstain(self, store):
        response = {
            "status": "INSUFFICIENT_SIGNAL",
            "confidence": 0.35,
        }
        call_id = store.log_call("Will unobtanium rise?", "commodity.exotic", response)
        call = store.get_call(call_id)
        assert call["status"] == "INSUFFICIENT_SIGNAL"
        assert call["direction"] is None

    def test_history_returns_recent_first(self, store):
        store.log_call("q1", "d1", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        store.log_call("q2", "d2", {"status": "ORACLE_RESPONSE", "view": {"direction": "bearish", "confidence": 0.6}})
        store.log_call("q3", "d3", {"status": "INSUFFICIENT_SIGNAL", "confidence": 0.3})

        history = store.get_history(limit=10)
        assert len(history) == 3
        assert history[0]["query"] == "q3"  # most recent first

    def test_history_filters_by_domain(self, store):
        store.log_call("q1", "commodity.energy.crude_oil", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        store.log_call("q2", "fx.major.eurusd", {"status": "ORACLE_RESPONSE", "view": {"direction": "bearish", "confidence": 0.6}})

        history = store.get_history(domain="commodity")
        assert len(history) == 1
        assert history[0]["domain"] == "commodity.energy.crude_oil"

    def test_record_outcome(self, store):
        call_id = store.log_call("q1", "d1", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        success = store.record_outcome(call_id, "correct", "Price rose 5% in 4 weeks")
        assert success is True

        call = store.get_call(call_id)
        assert call["outcome"] == "correct"
        assert call["notes"] == "Price rose 5% in 4 weeks"
        assert call["outcome_at"] is not None

    def test_track_record(self, store):
        r = {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}}
        id1 = store.log_call("q1", "d1", r)
        id2 = store.log_call("q2", "d1", r)
        id3 = store.log_call("q3", "d1", {"status": "INSUFFICIENT_SIGNAL", "confidence": 0.3})

        store.record_outcome(id1, "correct")
        store.record_outcome(id2, "incorrect")

        record = store.get_track_record()
        assert record["total_calls"] == 3
        assert record["responded"] == 2
        assert record["abstained"] == 1
        assert record["scored"] == 2
        assert record["win_rate"] == 0.5

    def test_get_nonexistent_call(self, store):
        assert store.get_call(9999) is None

    def test_record_outcome_nonexistent(self, store):
        assert store.record_outcome(9999, "correct") is False

    def test_clear(self, store):
        store.log_call("q1", "d1", {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}})
        store.clear()
        assert store.get_history() == []
