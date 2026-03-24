"""시그널 성과 추적 API 라우터"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_db
from db.repository import AnomalyRepository

router = APIRouter(prefix="/api/v1/performance", tags=["Performance"])


@router.get("/summary")
async def get_performance_summary(
    days: int = Query(default=30, ge=1, le=365, description="집계 기간 (일)"),
    db: AsyncSession = Depends(get_db),
):
    """
    전체 시그널 성과 요약.

    - `accuracy_24h_pct`: 급등 예측 후 24h 내 실제 상승 OR 급락 예측 후 실제 하락한 비율 (%)
    - `avg_return_Xh`: 평균 수익률 (이상감지 방향 무관, 단순 가격 변화율)
    """
    repo = AnomalyRepository(db)
    return await repo.get_performance_summary(days=days)


@router.get("/{ticker}")
async def get_ticker_performance(
    ticker: str,
    days: int = Query(default=90, ge=1, le=365, description="조회 기간 (일)"),
    db: AsyncSession = Depends(get_db),
):
    """
    종목별 시그널 성과 이력.

    각 이상감지 이벤트에 대해 감지 후 1h / 24h / 7d 수익률을 반환.
    아직 측정되지 않은 항목은 null로 반환됨.
    """
    repo = AnomalyRepository(db)
    records = await repo.get_ticker_performance(ticker=ticker.upper(), days=days)

    return [
        {
            "anomaly_id":     r.anomaly_id,
            "direction":      r.direction,
            "detected_price": r.detected_price,
            "return_1h":      r.return_1h,
            "return_24h":     r.return_24h,
            "return_1w":      r.return_1w,
            "created_at":     r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
