"""GET/POST /api/v1/predictions 라우터 - ML 주가 예측"""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_db
from db.models import StockPrediction, MLModelPerformance

# ── Prometheus 커스텀 메트릭 ─────────────────────────────────────────────
try:
    from prometheus_client import Counter, Gauge, Histogram

    ml_predictions_total = Counter(
        "ml_predictions_total",
        "ML 예측 생성 횟수",
        ["ticker", "direction"],
    )
    ml_prediction_accuracy = Gauge(
        "ml_prediction_accuracy",
        "ML 예측 30일 롤링 정확도 (0~1)",
        ["ticker"],
    )
    ml_train_duration_seconds = Histogram(
        "ml_train_duration_seconds",
        "ML 모델 학습 소요 시간(초)",
        ["ticker"],
        buckets=[10, 30, 60, 120, 300, 600],
    )
    ml_retrain_triggered_total = Counter(
        "ml_retrain_triggered_total",
        "재학습 트리거 횟수",
        ["ticker"],
    )
    _METRICS_ENABLED = True
except ImportError:
    _METRICS_ENABLED = False

router = APIRouter(prefix="/api/v1/predictions", tags=["Predictions"])


# ── 스키마 ────────────────────────────────────────────────────────────────

class PredictionResponse(BaseModel):
    id: int
    ticker: str
    prediction_date: date
    predicted_at: datetime
    direction: str
    up_prob: float
    confidence: float
    cv_accuracy: Optional[float]
    shap_top5: Optional[dict]
    model_version: Optional[str]
    actual_direction: Optional[str]
    actual_return: Optional[float]
    was_correct: Optional[bool]

    class Config:
        from_attributes = True


class ModelPerformanceResponse(BaseModel):
    ticker: str
    eval_date: date
    accuracy_7d: Optional[float]
    accuracy_30d: Optional[float]
    sample_count: int
    retrain_triggered: bool

    class Config:
        from_attributes = True


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@router.get("", response_model=list[PredictionResponse])
async def get_predictions(
    days: int = Query(7, ge=1, le=30),
    ticker: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """최근 ML 예측 목록"""
    since = date.today() - timedelta(days=days)
    stmt = (
        select(StockPrediction)
        .where(StockPrediction.prediction_date >= since)
        .order_by(desc(StockPrediction.prediction_date), desc(StockPrediction.confidence))
    )
    if ticker:
        stmt = stmt.where(StockPrediction.ticker == ticker.upper())
    result = await db.execute(stmt.limit(200))
    return result.scalars().all()


@router.get("/{ticker}/latest", response_model=PredictionResponse)
async def get_latest_prediction(ticker: str, db: AsyncSession = Depends(get_db)):
    """특정 종목 최신 예측"""
    stmt = (
        select(StockPrediction)
        .where(StockPrediction.ticker == ticker.upper())
        .order_by(desc(StockPrediction.prediction_date))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"{ticker} 예측 데이터 없음")
    return row


@router.get("/{ticker}/performance", response_model=list[ModelPerformanceResponse])
async def get_model_performance(
    ticker: str,
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """특정 종목 모델 성과 이력"""
    since = date.today() - timedelta(days=days)
    stmt = (
        select(MLModelPerformance)
        .where(
            MLModelPerformance.ticker == ticker.upper(),
            MLModelPerformance.eval_date >= since,
        )
        .order_by(desc(MLModelPerformance.eval_date))
    )
    rows = (await db.execute(stmt)).scalars().all()

    # 가장 최근 30일 정확도를 Prometheus Gauge에 업데이트
    if _METRICS_ENABLED and rows:
        latest = rows[0]
        if latest.accuracy_30d is not None:
            ml_prediction_accuracy.labels(ticker=ticker.upper()).set(latest.accuracy_30d)

    return rows


@router.post("/{ticker}/train")
async def trigger_training(ticker: str, background_tasks: BackgroundTasks):
    """ML 모델 즉시 학습 트리거 (백그라운드)"""
    if _METRICS_ENABLED:
        ml_retrain_triggered_total.labels(ticker=ticker.upper()).inc()
    background_tasks.add_task(_train_and_predict, ticker.upper())
    return {"message": f"{ticker} 모델 학습 시작", "ticker": ticker.upper()}


async def _train_and_predict(ticker: str):
    """백그라운드 학습 + 예측 작업"""
    import asyncio
    import logging
    import time

    logger = logging.getLogger(__name__)
    loop = asyncio.get_event_loop()

    try:
        from core.feature_engineer import build_feature_matrix, create_labels
        from core.ml_predictor import train, predict
        from db.connection import AsyncSessionLocal

        # 피처 수집 (동기 함수 → executor)
        features = await loop.run_in_executor(
            None, build_feature_matrix, ticker, 365, True
        )

        if features.empty:
            logger.warning(f"[Train] {ticker} 피처 수집 실패")
            return

        labels = create_labels(features["close"])

        # 학습 (소요 시간 측정)
        t0 = time.perf_counter()
        result = await loop.run_in_executor(None, train, ticker, features, labels)
        elapsed = time.perf_counter() - t0

        if _METRICS_ENABLED:
            ml_train_duration_seconds.labels(ticker=ticker).observe(elapsed)

        logger.info(f"[Train] {ticker} 완료: acc={result['cv_accuracy']:.4f} ({elapsed:.1f}s)")

        # 예측 저장
        pred = await loop.run_in_executor(None, predict, ticker, features)
        if pred:
            tomorrow = (datetime.now() + timedelta(days=1)).date()
            async with AsyncSessionLocal() as db:
                # 중복 방지: 오늘 이미 예측이 있으면 덮어쓰기
                existing = (await db.execute(
                    select(StockPrediction).where(
                        StockPrediction.ticker == ticker,
                        StockPrediction.prediction_date == tomorrow,
                    )
                )).scalar_one_or_none()

                if existing:
                    existing.direction     = pred["direction"]
                    existing.up_prob       = pred["up_prob"]
                    existing.confidence    = pred["confidence"]
                    existing.cv_accuracy   = pred.get("cv_accuracy")
                    existing.shap_top5     = pred.get("shap_top5")
                    existing.model_version = pred.get("model_train_date", "")[:10]
                else:
                    db.add(StockPrediction(
                        ticker=ticker,
                        prediction_date=tomorrow,
                        direction=pred["direction"],
                        up_prob=pred["up_prob"],
                        confidence=pred["confidence"],
                        cv_accuracy=pred.get("cv_accuracy"),
                        shap_top5=pred.get("shap_top5"),
                        model_version=pred.get("model_train_date", "")[:10],
                    ))
                await db.commit()

            if _METRICS_ENABLED:
                ml_predictions_total.labels(ticker=ticker, direction=pred["direction"]).inc()

            logger.info(f"[Train] {ticker} 예측 저장: {pred['direction']} ({pred['up_prob']}%)")

    except Exception as e:
        logger.error(f"[Train] {ticker} 실패: {e}")
