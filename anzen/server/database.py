"""
Async SQLite database via SQLAlchemy + aiosqlite.
Single file, zero config — perfect for self-hosting.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, JSON, Index, text
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from anzen.server.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


class EventModel(Base):
    __tablename__ = "events"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    event_id   = Column(String(64), unique=True, nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    guard_type = Column(String(16), nullable=False, index=True)
    action     = Column(String(16), nullable=False, index=True)
    category   = Column(String(32), nullable=False)
    risk_score = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)
    explanation= Column(String(512), default="")
    input_text = Column(String(1024), default="")
    input_params = Column(JSON, default=None)
    layer      = Column(Integer, default=0)
    latency_ms = Column(Float, default=0.0)
    cumulative_risk = Column(Float, default=0.0)
    metadata_  = Column("metadata", JSON, default=dict)
    timestamp  = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_events_timestamp_action", "timestamp", "action"),
        Index("ix_events_session_timestamp", "session_id", "timestamp"),
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    session_id      = Column(String(64), unique=True, nullable=False, index=True)
    first_seen      = Column(DateTime, nullable=False)
    last_seen       = Column(DateTime, nullable=False)
    total_events    = Column(Integer, default=0)
    blocked_events  = Column(Integer, default=0)
    alerted_events  = Column(Integer, default=0)
    max_risk_score  = Column(Float, default=0.0)
    cumulative_risk = Column(Float, default=0.0)
    is_flagged      = Column(Integer, default=0)   # boolean


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
