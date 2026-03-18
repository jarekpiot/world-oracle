"""
World Oracle — Signal Store (Async)
Persistence layer for oracle calls. The track record.

Async SQLAlchemy 2.0 — works with both PostgreSQL (production)
and SQLite+aiosqlite (local dev / tests).

Every query + response is logged. Outcomes are filled in later
when the market verdict is known.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import OracleCall, SignalLog
from db.engine import AsyncSessionLocal, init_db


class SignalStore:
    """
    Async database-backed store for oracle calls.
    Uses SQLAlchemy 2.0 async sessions.
    """

    def __init__(self):
        self._initialized = False

    async def ensure_tables(self):
        """Create tables if they don't exist. Idempotent."""
        if not self._initialized:
            await init_db()
            self._initialized = True

    async def log_call(self, query: str, domain: str, response: dict) -> int:
        """Log an oracle call. Returns the row ID."""
        await self.ensure_tables()

        status = response.get("status", "UNKNOWN")
        view = response.get("view", {})

        direction = view.get("direction") if status == "ORACLE_RESPONSE" else None
        confidence = view.get("confidence") if status == "ORACLE_RESPONSE" else response.get("confidence")
        band = view.get("band", "") if status == "ORACLE_RESPONSE" else ""
        alignment = view.get("alignment") if status == "ORACLE_RESPONSE" else None
        thesis = view.get("thesis", "") if status == "ORACLE_RESPONSE" else ""
        invalidators = response.get("risk", {}).get("invalidators", []) if status == "ORACLE_RESPONSE" else []

        # Parse band
        band_low = band_high = None
        if band and isinstance(band, str):
            try:
                parts = band.replace("\u2013", "-").replace("–", "-").split("-")
                if len(parts) == 2:
                    band_low = float(parts[0].strip())
                    band_high = float(parts[1].strip())
            except (ValueError, IndexError):
                pass

        row = OracleCall(
            query=query,
            domain=domain,
            status=status,
            direction=direction,
            confidence=confidence,
            band_low=band_low,
            band_high=band_high,
            alignment=alignment,
            thesis=thesis,
            invalidators=invalidators,
            full_response=response,
        )

        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def log_signals(self, call_id: int, signals: list) -> None:
        """Log individual agent signals for a call."""
        await self.ensure_tables()

        rows = []
        for s in signals:
            rows.append(SignalLog(
                call_id=call_id,
                agent_id=getattr(s, 'agent_id', str(s.get('agent', ''))),
                domain=getattr(s, 'domain_path', str(s.get('domain', ''))),
                direction=getattr(s, 'direction', s.get('direction', '')).value
                    if hasattr(getattr(s, 'direction', None), 'value')
                    else str(s.get('direction', '')),
                confidence=getattr(s, 'confidence', s.get('confidence', 0)),
                temporal_layer=getattr(s, 'temporal_layer', s.get('layer', '')).value
                    if hasattr(getattr(s, 'temporal_layer', None), 'value')
                    else str(s.get('layer', '')),
                reasoning=getattr(s, 'reasoning', s.get('reasoning', ''))[:500],
                decay_triggers=getattr(s, 'decay_triggers', s.get('decay_triggers', [])),
            ))

        async with AsyncSessionLocal() as session:
            session.add_all(rows)
            await session.commit()

    async def record_outcome(self, call_id: int, outcome: str, notes: str = "") -> bool:
        """Record the market outcome for a past oracle call."""
        await self.ensure_tables()
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(OracleCall)
                .where(OracleCall.id == call_id)
                .values(outcome=outcome, outcome_notes=notes, resolved_at=now)
            )
            await session.commit()
            return result.rowcount > 0

    async def get_history(self, limit: int = 50, domain: Optional[str] = None) -> list[dict]:
        """Get recent oracle calls, most recent first."""
        await self.ensure_tables()

        async with AsyncSessionLocal() as session:
            stmt = select(OracleCall).order_by(OracleCall.created_at.desc()).limit(limit)
            if domain:
                stmt = stmt.where(OracleCall.domain.like(f"{domain}%"))

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [
                {
                    "id": r.id,
                    "query": r.query,
                    "domain": r.domain,
                    "timestamp": r.created_at.isoformat() if r.created_at else None,
                    "status": r.status,
                    "direction": r.direction,
                    "confidence": r.confidence,
                    "outcome": r.outcome,
                    "outcome_at": r.resolved_at.isoformat() if r.resolved_at else None,
                    "notes": r.outcome_notes,
                }
                for r in rows
            ]

    async def get_call(self, call_id: int) -> Optional[dict]:
        """Get a single oracle call by ID."""
        await self.ensure_tables()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OracleCall).where(OracleCall.id == call_id)
            )
            r = result.scalar_one_or_none()
            if not r:
                return None

            return {
                "id": r.id,
                "query": r.query,
                "domain": r.domain,
                "timestamp": r.created_at.isoformat() if r.created_at else None,
                "status": r.status,
                "direction": r.direction,
                "confidence": r.confidence,
                "alignment": r.alignment,
                "thesis": r.thesis,
                "outcome": r.outcome,
                "outcome_at": r.resolved_at.isoformat() if r.resolved_at else None,
                "notes": r.outcome_notes,
                "response": r.full_response,
            }

    async def get_track_record(self, domain: Optional[str] = None) -> dict:
        """Aggregate track record statistics."""
        await self.ensure_tables()

        async with AsyncSessionLocal() as session:
            stmt = select(OracleCall)
            if domain:
                stmt = stmt.where(OracleCall.domain.like(f"{domain}%"))
            result = await session.execute(stmt)
            rows = result.scalars().all()

            total = len(rows)
            responded = sum(1 for r in rows if r.status == "ORACLE_RESPONSE")
            abstained = sum(1 for r in rows if r.status == "INSUFFICIENT_SIGNAL")
            outcomes = {}
            for r in rows:
                if r.outcome:
                    outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
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

    async def clear(self):
        """Clear all data. For testing only."""
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            await session.execute(OracleCall.__table__.delete())
            await session.execute(SignalLog.__table__.delete())
            await session.commit()
