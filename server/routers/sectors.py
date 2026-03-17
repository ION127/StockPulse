"""GET /api/v1/sectors 라우터"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.connection import get_db
from server.db.repository import AnomalyRepository
from server.schemas.anomaly import SectorTrendItem

router = APIRouter(prefix="/api/v1/sectors", tags=["Sectors"])


@router.get("/trending", response_model=list[SectorTrendItem])
async def get_trending_sectors(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    repo = AnomalyRepository(db)
    trends = await repo.get_sector_trends(days=days)
    return [
        SectorTrendItem(
            sector=row["sector"],
            anomaly_count=row["anomaly_count"],
            avg_return_pct=round(float(row["avg_return_pct"] or 0), 2),
            up_count=int(row["up_count"] or 0),
            down_count=int(row["down_count"] or 0),
            hot_tickers=row["hot_tickers"],
        )
        for row in trends
    ]
