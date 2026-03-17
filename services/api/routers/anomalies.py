"""GET /api/v1/anomalies 라우터"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_db
from db.repository import AnomalyRepository
from schemas.anomaly import AnomalyResponse, AnalysisResponse, NewsArticle

router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomalies"])


@router.get("", response_model=list[AnomalyResponse])
async def get_anomalies(
    days: int = Query(7, ge=1, le=90),
    sector: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    repo = AnomalyRepository(db)
    anomalies = await repo.get_recent_anomalies(days=days, sector=sector,
                                                event_type=event_type, limit=limit)
    return [
        AnomalyResponse(
            **{c.name: getattr(a, c.name) for c in a.__table__.columns},
            has_analysis=a.analysis is not None,
        )
        for a in anomalies
    ]


@router.get("/{ticker}/history", response_model=list[AnomalyResponse])
async def get_ticker_history(
    ticker: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    repo = AnomalyRepository(db)
    anomalies = await repo.get_ticker_history(ticker=ticker.upper(), days=days)
    if not anomalies:
        raise HTTPException(status_code=404, detail=f"{ticker} 이상값 이력 없음")
    return [
        AnomalyResponse(
            **{c.name: getattr(a, c.name) for c in a.__table__.columns},
            has_analysis=a.analysis is not None,
        )
        for a in anomalies
    ]


@router.get("/{anomaly_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(anomaly_id: int, db: AsyncSession = Depends(get_db)):
    repo = AnomalyRepository(db)
    result = await repo.get_analysis(anomaly_id)
    if not result:
        raise HTTPException(status_code=404, detail="분석 결과 없음")
    return AnalysisResponse(
        id=result.id, anomaly_id=result.anomaly_id, created_at=result.created_at,
        analysis_ko=result.analysis_ko, analysis_en=result.analysis_en,
        news_en=[NewsArticle(**n) for n in (result.news_en or [])],
        news_kr=[NewsArticle(**n) for n in (result.news_kr or [])],
    )
