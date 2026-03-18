"""
World Oracle — Signal Store
Persistence layer for oracle calls. The track record.

Every query + response is logged. Outcomes are filled in later
when the market verdict is known. This store is what makes
Tier 2 monetisation possible — a verifiable track record.

SQLite for now. Swap to PostgreSQL for production.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


DEFAULT_DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///world_oracle.db")


def _resolve_path(db_url: str) -> str:
    """Convert DATABASE_URL format to file path."""
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///"):]
    return db_url


class SignalStore:
    """
    SQLite-backed store for oracle calls.
    Every query, response, and eventual outcome is persisted.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = _resolve_path(db_path or DEFAULT_DB_PATH)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS oracle_calls (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    query       TEXT NOT NULL,
                    domain      TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    direction   TEXT,
                    confidence  REAL,
                    response    TEXT NOT NULL,
                    outcome     TEXT,
                    outcome_at  TEXT,
                    notes       TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_oracle_calls_domain
                    ON oracle_calls(domain);
                CREATE INDEX IF NOT EXISTS idx_oracle_calls_timestamp
                    ON oracle_calls(timestamp);
                CREATE INDEX IF NOT EXISTS idx_oracle_calls_status
                    ON oracle_calls(status);
            """)
            conn.commit()
        finally:
            conn.close()

    def log_call(self, query: str, domain: str, response: dict) -> int:
        """
        Log an oracle call. Returns the row ID.
        Called automatically by the API after every query.
        """
        now = datetime.now(timezone.utc).isoformat()
        status = response.get("status", "UNKNOWN")

        # Extract direction and confidence from response
        view = response.get("view", {})
        direction = view.get("direction") if status == "ORACLE_RESPONSE" else None
        confidence = view.get("confidence") if status == "ORACLE_RESPONSE" else response.get("confidence")

        conn = self._connect()
        try:
            cursor = conn.execute(
                """INSERT INTO oracle_calls
                   (query, domain, timestamp, status, direction, confidence, response)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (query, domain, now, status, direction, confidence, json.dumps(response)),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def record_outcome(self, call_id: int, outcome: str, notes: str = "") -> bool:
        """
        Record the market outcome for a past oracle call.
        outcome: "correct", "incorrect", "partial", "inconclusive"
        This is what builds the track record.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE oracle_calls
                   SET outcome = ?, outcome_at = ?, notes = ?
                   WHERE id = ?""",
                (outcome, now, notes, call_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_history(self, limit: int = 50, domain: Optional[str] = None) -> list[dict]:
        """
        Get recent oracle calls. Ordered by most recent first.
        Optionally filter by domain.
        """
        conn = self._connect()
        try:
            if domain:
                rows = conn.execute(
                    """SELECT id, query, domain, timestamp, status, direction,
                              confidence, outcome, outcome_at, notes
                       FROM oracle_calls
                       WHERE domain LIKE ?
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (f"{domain}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, query, domain, timestamp, status, direction,
                              confidence, outcome, outcome_at, notes
                       FROM oracle_calls
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_call(self, call_id: int) -> Optional[dict]:
        """Get a single oracle call by ID, including full response."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM oracle_calls WHERE id = ?", (call_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["response"] = json.loads(result["response"])
            return result
        finally:
            conn.close()

    def get_track_record(self, domain: Optional[str] = None) -> dict:
        """
        Aggregate track record statistics.
        Returns win rate, total calls, outcomes breakdown.
        """
        conn = self._connect()
        try:
            base_query = "SELECT status, direction, confidence, outcome FROM oracle_calls"
            params = []

            if domain:
                base_query += " WHERE domain LIKE ?"
                params.append(f"{domain}%")

            rows = conn.execute(base_query, params).fetchall()

            total = len(rows)
            responded = sum(1 for r in rows if r["status"] == "ORACLE_RESPONSE")
            abstained = sum(1 for r in rows if r["status"] == "INSUFFICIENT_SIGNAL")

            outcomes = {}
            for r in rows:
                if r["outcome"]:
                    outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1

            scored = sum(outcomes.values())
            correct = outcomes.get("correct", 0)
            win_rate = (correct / scored) if scored > 0 else None

            return {
                "total_calls": total,
                "responded": responded,
                "abstained": abstained,
                "scored": scored,
                "outcomes": outcomes,
                "win_rate": round(win_rate, 3) if win_rate is not None else None,
            }
        finally:
            conn.close()

    def clear(self):
        """Clear all data. For testing only."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM oracle_calls")
            conn.commit()
        finally:
            conn.close()
