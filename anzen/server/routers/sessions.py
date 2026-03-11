from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anzen.server.auth import verify_api_key
from anzen.server.database import SessionModel, get_db

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/sessions")
async def list_sessions(
    limit: int = 50,
    flagged_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(SessionModel).order_by(SessionModel.last_seen.desc()).limit(limit)
    if flagged_only:
        q = q.where(SessionModel.is_flagged == 1)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "session_id": r.session_id,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            "total_events": r.total_events,
            "blocked_events": r.blocked_events,
            "alerted_events": r.alerted_events,
            "max_risk_score": r.max_risk_score,
            "cumulative_risk": r.cumulative_risk,
            "is_flagged": bool(r.is_flagged),
        }
        for r in rows
    ]
