"""
World Oracle — Database Models
SQLAlchemy 2.0 async ORM models.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, JSON,
    DateTime, func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OracleCall(Base):
    __tablename__ = "oracle_calls"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    query         = Column(Text, nullable=False)
    domain        = Column(String(100))
    status        = Column(String(50))
    direction     = Column(String(20))
    confidence    = Column(Float)
    band_low      = Column(Float)
    band_high     = Column(Float)
    alignment     = Column(Float)
    thesis        = Column(Text)
    invalidators  = Column(JSON)
    full_response = Column(JSON)
    outcome       = Column(String(20))    # pending | correct | incorrect | partial | inconclusive
    outcome_notes = Column(Text)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at   = Column(DateTime(timezone=True))


class SignalLog(Base):
    __tablename__ = "signal_log"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    call_id        = Column(Integer)
    agent_id       = Column(String(100))
    domain         = Column(String(100))
    direction      = Column(String(20))
    confidence     = Column(Float)
    temporal_layer = Column(String(20))
    reasoning      = Column(Text)
    decay_triggers = Column(JSON)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
