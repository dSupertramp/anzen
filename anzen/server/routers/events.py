"""
POST /api/events — receives events from SDK, persists, broadcasts to dashboard.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anzen.server.auth import verify_api_key
from anzen.server.database import EventModel, SessionModel, get_db
from anzen.server.ws_manager import manager

router = APIRouter(dependencies=[Depends(verify_api_key)])


class IncomingEvent(BaseModel):
    event_id: str
    session_id: str
    guard_type: str
    action: str
    category: str
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    explanation: str = ""
    input_text: str | None = None
    input_params: dict[str, Any] | None = None
    layer: int = 0
    latency_ms: float = 0.0
    cumulative_risk: float = 0.0
    metadata: dict[str, Any] = {}
    timestamp: float  # unix timestamp


@router.post("/events", status_code=201)
async def ingest_event(event: IncomingEvent, db: AsyncSession = Depends(get_db)):
    # Deduplicate
    existing = await db.execute(select(EventModel).where(EventModel.event_id == event.event_id))
    if existing.scalar_one_or_none():
        return {"status": "duplicate"}

    ts = datetime.utcfromtimestamp(event.timestamp)

    # Persist event
    db_event = EventModel(
        event_id=event.event_id,
        session_id=event.session_id,
        guard_type=event.guard_type,
        action=event.action,
        category=event.category,
        risk_score=event.risk_score,
        confidence=event.confidence,
        explanation=event.explanation,
        input_text=(event.input_text or "")[:1024],
        input_params=event.input_params,
        layer=event.layer,
        latency_ms=event.latency_ms,
        cumulative_risk=event.cumulative_risk,
        metadata_=event.metadata,
        timestamp=ts,
    )
    db.add(db_event)

    # Upsert session
    session_row = await db.execute(select(SessionModel).where(SessionModel.session_id == event.session_id))
    sess = session_row.scalar_one_or_none()
    if sess is None:
        sess = SessionModel(
            session_id=event.session_id,
            first_seen=ts,
            last_seen=ts,
            total_events=0,
            blocked_events=0,
            alerted_events=0,
            max_risk_score=0.0,
            cumulative_risk=0.0,
        )
        db.add(sess)

    sess.last_seen = ts
    sess.total_events += 1
    sess.max_risk_score = max(sess.max_risk_score, event.risk_score)
    sess.cumulative_risk = event.cumulative_risk
    if event.action == "block":
        sess.blocked_events += 1
        sess.is_flagged = 1
    elif event.action == "alert":
        sess.alerted_events += 1

    await db.commit()

    # Broadcast to all dashboard WebSocket clients
    await manager.broadcast(
        {
            "type": "event",
            "data": event.model_dump(),
        }
    )

    return {"status": "ok", "event_id": event.event_id}


@router.get("/events")
async def list_events(
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    guard_type: str | None = None,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(1, limit), 10000)  # cap for export
    q = select(EventModel).order_by(EventModel.timestamp.desc())
    if action:
        q = q.where(EventModel.action == action)
    if guard_type:
        q = q.where(EventModel.guard_type == guard_type)
    if session_id:
        q = q.where(EventModel.session_id == session_id)
    q = q.limit(limit).offset(offset)

    result = await db.execute(q)
    rows = result.scalars().all()
    return [_event_to_dict(r) for r in rows]


def _event_to_dict(r: EventModel) -> dict:
    return {
        "event_id": r.event_id,
        "session_id": r.session_id,
        "guard_type": r.guard_type,
        "action": r.action,
        "category": r.category,
        "risk_score": r.risk_score,
        "confidence": r.confidence,
        "explanation": r.explanation,
        "input_text": r.input_text,
        "input_params": r.input_params,
        "layer": r.layer,
        "latency_ms": r.latency_ms,
        "cumulative_risk": r.cumulative_risk,
        "metadata": r.metadata_,
        "timestamp": r.timestamp.isoformat() + "Z" if r.timestamp else None,  # Add Z for UTC
    }
