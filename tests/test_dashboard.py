"""
Dashboard Tests — verify the dashboard module loads and pages are defined.
Run: python -m pytest tests/test_dashboard.py -v
"""

import os
import pytest

# Force SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test_dashboard.db")


class TestDashboardStructure:

    def test_app_module_imports(self):
        """Dashboard app.py should be importable (catches syntax errors)."""
        import py_compile
        py_compile.compile("dashboard/app.py", doraise=True)

    def test_visual_html_exists(self):
        """Breathing visualization HTML exists."""
        assert os.path.exists("dashboard/visual/index.html")

    def test_feed_monitor_used_by_dashboard(self):
        """Feed monitor (used by dashboard) initialises correctly."""
        from core.registry import ModuleRegistry
        from core.feed_monitor import FeedMonitor

        registry = ModuleRegistry()
        monitor = FeedMonitor(registry)
        summary = monitor.summary()
        assert summary["status"] == "no_check_run"
