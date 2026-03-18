"""
Dashboard Tests — verify the dashboard module loads and pages are defined.
Run: python -m pytest tests/test_dashboard.py -v

Note: Full Streamlit app testing requires streamlit.testing which is
session-based. These tests verify the structural integrity of the app.
"""

import pytest
import importlib


class TestDashboardStructure:

    def test_app_module_imports(self):
        """Dashboard app.py should be importable (catches syntax errors)."""
        # We can't fully import app.py because it calls st.set_page_config
        # at module level. Instead, verify the file exists and has no syntax errors.
        import py_compile
        py_compile.compile("dashboard/app.py", doraise=True)

    def test_signal_store_works_with_dashboard(self, tmp_path):
        """Signal store (used by dashboard) works correctly."""
        from db.signal_store import SignalStore

        store = SignalStore(db_path=str(tmp_path / "dash_test.db"))
        call_id = store.log_call(
            "test query", "commodity.energy",
            {"status": "ORACLE_RESPONSE", "view": {"direction": "bullish", "confidence": 0.7}},
        )
        history = store.get_history(limit=10)
        assert len(history) == 1
        assert history[0]["query"] == "test query"

    def test_feed_monitor_used_by_dashboard(self):
        """Feed monitor (used by dashboard) initialises correctly."""
        from core.registry import ModuleRegistry
        from core.feed_monitor import FeedMonitor

        registry = ModuleRegistry()
        monitor = FeedMonitor(registry)
        summary = monitor.summary()
        assert summary["status"] == "no_check_run"
