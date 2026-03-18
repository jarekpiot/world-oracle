"""
World Oracle — Feed Health Monitor
Runs health checks across all registered modules.
Triggers on startup and every 15 minutes.
Logs stale feeds as warnings.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.registry import ModuleRegistry

logger = logging.getLogger("world_oracle.feed_monitor")


class FeedMonitor:
    """
    Monitors data feed health across all registered modules.
    Calls module.health_check() for each module and aggregates results.
    """

    def __init__(self, registry: ModuleRegistry):
        self.registry = registry
        self._last_check: Optional[dict] = None
        self._last_check_at: Optional[str] = None

    async def check_all_feeds(self) -> dict:
        """
        Run health checks on all registered modules.
        Returns {module_id: {feed_id: {status, last_updated, staleness}}}
        """
        results = {}

        for module_info in self.registry.list_modules():
            module_id = module_info["id"]
            prefix = module_info["prefix"]
            module = self.registry.resolve(prefix)

            if not module:
                results[module_id] = {"status": "error", "message": "Module not resolvable"}
                continue

            try:
                health = await module.health_check()
                feeds = health.get("feeds", {})

                module_result = {}
                for feed_id, feed_health in feeds.items():
                    status = feed_health.get("status", "unknown")
                    module_result[feed_id] = {
                        "status": status,
                        "last_fetched": feed_health.get("last_fetched"),
                        "message": feed_health.get("message", ""),
                    }

                    # Log warnings for unhealthy feeds
                    if status not in ("ok", "partial"):
                        logger.warning(
                            "Feed %s in module %s is unhealthy: %s",
                            feed_id, module_id, feed_health.get("message", status),
                        )

                results[module_id] = module_result

            except Exception as e:
                logger.error("Health check failed for module %s: %s", module_id, e)
                results[module_id] = {"status": "error", "message": str(e)}

        self._last_check = results
        self._last_check_at = datetime.now(timezone.utc).isoformat()

        return results

    @property
    def last_check(self) -> Optional[dict]:
        return self._last_check

    @property
    def last_check_at(self) -> Optional[str]:
        return self._last_check_at

    def summary(self) -> dict:
        """Quick summary of feed health."""
        if not self._last_check:
            return {"status": "no_check_run", "checked_at": None}

        total_feeds = 0
        healthy = 0
        unhealthy = 0
        warnings = []

        for module_id, feeds in self._last_check.items():
            if isinstance(feeds, dict) and "status" in feeds and feeds["status"] == "error":
                unhealthy += 1
                warnings.append(f"{module_id}: {feeds.get('message', 'error')}")
                continue

            for feed_id, feed_data in feeds.items():
                if not isinstance(feed_data, dict):
                    continue
                total_feeds += 1
                status = feed_data.get("status", "unknown")
                if status == "ok":
                    healthy += 1
                else:
                    unhealthy += 1
                    warnings.append(f"{module_id}/{feed_id}: {status}")

        return {
            "status": "healthy" if unhealthy == 0 else "degraded",
            "checked_at": self._last_check_at,
            "total_feeds": total_feeds,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "warnings": warnings,
        }


async def run_periodic_health_check(
    registry: ModuleRegistry,
    interval_seconds: int = 900,
):
    """
    Background task: run feed health checks every interval_seconds.
    Meant to be started as an asyncio task on server startup.
    """
    monitor = FeedMonitor(registry)
    logger.info("Feed monitor starting — checking every %ds", interval_seconds)

    while True:
        try:
            results = await monitor.check_all_feeds()
            summary = monitor.summary()
            if summary["unhealthy"] > 0:
                logger.warning("Feed health: %d/%d feeds unhealthy",
                               summary["unhealthy"], summary["total_feeds"])
            else:
                logger.info("Feed health: all %d feeds healthy", summary["total_feeds"])
        except Exception as e:
            logger.error("Feed monitor error: %s", e)

        await asyncio.sleep(interval_seconds)
