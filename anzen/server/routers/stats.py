from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anzen.server.auth import verify_api_key
from anzen.server.database import EventModel, get_db

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)

    # Total counts
    total = await _count(db, EventModel)
    blocked = await _count(db, EventModel, EventModel.action == "block")
    alerted = await _count(db, EventModel, EventModel.action == "alert")
    last_hour = await _count(db, EventModel, EventModel.timestamp >= one_hour_ago)
    last_day = await _count(db, EventModel, EventModel.timestamp >= one_day_ago)

    # Avg risk & latency
    avg_risk = await db.execute(select(func.avg(EventModel.risk_score)))
    avg_lat = await db.execute(select(func.avg(EventModel.latency_ms)))

    # By guard type
    by_guard = await db.execute(select(EventModel.guard_type, func.count()).group_by(EventModel.guard_type))

    # By category
    by_category = await db.execute(
        select(EventModel.category, func.count()).group_by(EventModel.category).order_by(func.count().desc()).limit(10)
    )

    # Risk timeline — last 60 events grouped in buckets of 5
    timeline = await db.execute(
        select(EventModel.risk_score, EventModel.timestamp).order_by(EventModel.timestamp.desc()).limit(60)
    )

    return {
        "total": total,
        "blocked": blocked,
        "alerted": alerted,
        "allowed": total - blocked - alerted,
        "last_hour": last_hour,
        "last_day": last_day,
        "avg_risk": round(avg_risk.scalar() or 0, 3),
        "avg_latency_ms": round(avg_lat.scalar() or 0, 1),
        "block_rate": round(blocked / total * 100, 1) if total else 0,
        "by_guard": dict(by_guard.all()),
        "by_category": dict(by_category.all()),
        "risk_timeline": [{"score": r.risk_score, "ts": r.timestamp.isoformat()} for r in reversed(timeline.all())],
    }


async def _count(db, model, *conditions):
    q = select(func.count()).select_from(model)
    for c in conditions:
        q = q.where(c)
    result = await db.execute(q)
    return result.scalar() or 0
