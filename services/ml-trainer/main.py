"""
ML 트레이너 서비스 (Kubernetes CronJob)
- 매일 장 마감 후 실행 (17:00 KST)
- 전체 추적 종목 피처 수집 → 학습 → 예측 → DB 저장
- 전일 예측 결과 검증 → 정확도 기록 → 재학습 트리거

환경변수:
    DATABASE_URL       : PostgreSQL 연결 문자열
    MODEL_DIR          : 모델 파일 저장 경로 (default: /app/models)
    DART_API_KEY       : DART API 키 (선택, 재무데이터)
    BOK_API_KEY        : 한국은행 API 키 (선택, 기준금리)
    ML_RETRAIN_THRESHOLD: 재학습 임계값 (default: 0.52)
    ML_TICKERS         : 학습할 종목 코드 목록, 콤마 구분 (default: 주요 종목)
    ML_DAYS_BACK       : 학습 데이터 기간 일수 (default: 365)
"""

import asyncio
import logging
import os
import sys
from datetime import date, datetime, timedelta


# ── 한국 거래소 공휴일 체크 ───────────────────────────────────────────────

def _is_kr_trading_day(target_date: date | None = None) -> bool:
    """
    한국 주식 시장 거래일 여부 확인
    - pykrx 사용 (실제 KRX 휴장일 반영)
    - pykrx 미설치 시 토/일 + 고정 공휴일 기반 fallback
    """
    if target_date is None:
        target_date = date.today()

    # 주말은 항상 휴장
    if target_date.weekday() >= 5:
        return False

    try:
        from pykrx import stock as krx_stock
        # get_market_ohlcv 빈 결과 → 휴장일
        df = krx_stock.get_market_ohlcv(
            target_date.strftime("%Y%m%d"),
            target_date.strftime("%Y%m%d"),
            "005930",  # 삼성전자로 대표 확인
        )
        return not df.empty

    except Exception:
        # fallback: 고정 공휴일 (매년 동일한 날짜만)
        _FIXED_HOLIDAYS = {(1, 1), (3, 1), (5, 5), (6, 6), (8, 15),
                           (10, 3), (10, 9), (12, 25)}
        return (target_date.month, target_date.day) not in _FIXED_HOLIDAYS

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ml-trainer")

# ── DB 설정 ──────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://stock:stock1234@localhost:5432/stockdb")
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# ── 기본 추적 종목 ────────────────────────────────────────────────────────

DEFAULT_TICKERS = [
    "KR:005930",  # 삼성전자
    "KR:000660",  # SK하이닉스
    "KR:035420",  # NAVER
    "KR:035720",  # 카카오
    "KR:051910",  # LG화학
    "KR:006400",  # 삼성SDI
    "KR:068270",  # 셀트리온
    "KR:207940",  # 삼성바이오로직스
    "KR:005380",  # 현대차
    "KR:000270",  # 기아
    "KR:105560",  # KB금융
    "KR:055550",  # 신한지주
    "KR:096770",  # SK이노베이션
    "KR:017670",  # SK텔레콤
    "KR:030200",  # KT
]

TICKERS = [t.strip() for t in os.getenv("ML_TICKERS", "").split(",") if t.strip()] or DEFAULT_TICKERS
DAYS_BACK = int(os.getenv("ML_DAYS_BACK", "365"))
MODEL_DIR = os.getenv("MODEL_DIR", "/app/models")
# 실행 모드: daily(기본) | weekly(Optuna 풀재학습) | verify(검증만)
RUN_MODE = os.getenv("ML_RUN_MODE", "daily")


# ── DB 모델 (API 서비스와 공유 테이블) ───────────────────────────────────

class Base(DeclarativeBase):
    pass


async def _ensure_tables():
    """ML 테이블이 없으면 생성"""
    # API 서비스가 이미 생성했을 가능성 높음 — 없는 경우 대비
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS stock_predictions (
                    id               SERIAL PRIMARY KEY,
                    ticker           VARCHAR(20)  NOT NULL,
                    prediction_date  DATE         NOT NULL,
                    predicted_at     TIMESTAMPTZ  DEFAULT NOW(),
                    direction        VARCHAR(10)  NOT NULL,
                    up_prob          FLOAT        NOT NULL,
                    confidence       FLOAT,
                    cv_accuracy      FLOAT,
                    shap_top5        JSONB,
                    model_version    VARCHAR(50),
                    actual_direction VARCHAR(10),
                    actual_return    FLOAT,
                    was_correct      BOOLEAN
                );
                CREATE INDEX IF NOT EXISTS idx_pred_ticker_date
                    ON stock_predictions (ticker, prediction_date);
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ml_model_performance (
                    id                 SERIAL PRIMARY KEY,
                    ticker             VARCHAR(20) NOT NULL,
                    eval_date          DATE        NOT NULL,
                    accuracy_7d        FLOAT,
                    accuracy_30d       FLOAT,
                    sample_count       INT DEFAULT 0,
                    retrain_triggered  BOOLEAN DEFAULT FALSE,
                    created_at         TIMESTAMPTZ DEFAULT NOW()
                );
            """))
        logger.info("ML 테이블 확인 완료")
    except Exception as e:
        logger.warning(f"테이블 생성 경고 (무시 가능): {e}")


# ── 핵심 작업 ─────────────────────────────────────────────────────────────

async def process_ticker(ticker: str, loop: asyncio.AbstractEventLoop) -> dict:
    """
    단일 종목 처리: 피처 수집 → 학습 → 예측 → DB 저장

    Returns: dict(ticker, status, cv_accuracy, direction)
    """
    from core.feature_engineer import build_feature_matrix, create_labels
    from core.ml_predictor import train, predict, model_exists, should_retrain, get_model_meta

    logger.info(f"[{ticker}] 처리 시작")

    try:
        # 1. 피처 수집 (느린 작업 → executor)
        features = await loop.run_in_executor(
            None, build_feature_matrix, ticker, DAYS_BACK, True
        )
        if features.empty or len(features) < 60:
            return {"ticker": ticker, "status": "skip", "reason": "데이터 부족"}

        labels = create_labels(features["close"], horizon=1)

        # 2. 학습 (모델 없거나 재학습 필요 시)
        needs_train = not model_exists(ticker)
        if not needs_train:
            # 최근 30일 예측 정확도 확인
            async with SessionLocal() as db:
                recent_acc = await _get_recent_accuracy(db, ticker, days=30)
            if recent_acc is not None:
                needs_train = should_retrain(ticker, recent_acc)
            # 정확도 데이터 없음(초기 7일) → 주간 CronJob이 재학습 담당, daily는 스킵

        train_result = None
        if needs_train:
            logger.info(f"[{ticker}] 모델 학습 시작")
            train_result = await loop.run_in_executor(None, train, ticker, features, labels)
            logger.info(f"[{ticker}] 학습 완료: acc={train_result['cv_accuracy']:.4f}")

        # 3. 예측
        pred = await loop.run_in_executor(None, predict, ticker, features)
        if not pred:
            return {"ticker": ticker, "status": "predict_failed"}

        # 4. DB 저장
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        async with SessionLocal() as db:
            # 중복 방지: 오늘 이미 저장된 예측이 있으면 스킵
            existing = await db.execute(
                select(StockPrediction)
                .where(
                    StockPrediction.ticker == ticker,
                    StockPrediction.prediction_date == tomorrow,
                )
            )
            if existing.scalar_one_or_none() is None:
                meta = get_model_meta(ticker)
                row = StockPrediction(
                    ticker=ticker,
                    prediction_date=tomorrow,
                    direction=pred["direction"],
                    up_prob=pred["up_prob"],
                    confidence=pred["confidence"],
                    cv_accuracy=pred.get("cv_accuracy"),
                    shap_top5=pred.get("shap_top5"),
                    model_version=(meta or {}).get("train_date", "")[:10],
                )
                db.add(row)
                await db.commit()

        logger.info(f"[{ticker}] 예측 저장: {pred['direction']} "
                    f"(상승확률={pred['up_prob']}%, 신뢰도={pred['confidence']}%)")

        return {
            "ticker":      ticker,
            "status":      "ok",
            "cv_accuracy": pred.get("cv_accuracy"),
            "direction":   pred["direction"],
            "up_prob":     pred["up_prob"],
        }

    except Exception as e:
        logger.error(f"[{ticker}] 처리 실패: {e}", exc_info=True)
        return {"ticker": ticker, "status": "error", "reason": str(e)}


async def _get_recent_accuracy(db: AsyncSession, ticker: str, days: int = 30) -> float | None:
    """DB에서 최근 N일 예측 정확도 계산"""
    since = date.today() - timedelta(days=days)
    stmt = select(StockPrediction).where(
        StockPrediction.ticker == ticker,
        StockPrediction.prediction_date >= since,
        StockPrediction.was_correct.is_not(None),
    )
    rows = (await db.execute(stmt)).scalars().all()
    if len(rows) < 5:
        return None
    correct = sum(1 for r in rows if r.was_correct)
    return correct / len(rows)


async def verify_yesterday_predictions():
    """
    전일 예측 결과 검증
    실제 주가와 비교하여 was_correct 업데이트
    """
    from core.collectors.krx_collector import get_ohlcv

    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    today_str = date.today().strftime("%Y%m%d")

    async with SessionLocal() as db:
        stmt = select(StockPrediction).where(
            StockPrediction.prediction_date == date.today() - timedelta(days=1),
            StockPrediction.was_correct.is_(None),
        )
        preds = (await db.execute(stmt)).scalars().all()

        if not preds:
            logger.info("검증할 전일 예측 없음")
            return

        loop = asyncio.get_event_loop()
        for pred in preds:
            try:
                ohlcv = await loop.run_in_executor(
                    None, get_ohlcv, pred.ticker, yesterday, today_str
                )
                if ohlcv.empty or len(ohlcv) < 2:
                    continue

                # 전날 → 당일 수익률
                prices = ohlcv["close"].values
                actual_return = (prices[-1] - prices[-2]) / prices[-2] * 100
                actual_direction = "상승" if actual_return > 0 else "하락"

                pred.actual_direction = actual_direction
                pred.actual_return    = round(actual_return, 4)
                pred.was_correct      = (pred.direction == actual_direction)

                logger.info(
                    f"[검증] {pred.ticker}: 예측={pred.direction}, "
                    f"실제={actual_direction} ({'O' if pred.was_correct else 'X'})"
                )
            except Exception as e:
                logger.warning(f"[검증] {pred.ticker} 실패: {e}")

        await db.commit()
        logger.info(f"전일 예측 {len(preds)}건 검증 완료")


async def record_model_performance():
    """
    각 종목별 롤링 정확도 계산 및 저장
    재학습 트리거 여부도 함께 기록
    """
    from core.ml_predictor import should_retrain

    today = date.today()
    async with SessionLocal() as db:
        for ticker in TICKERS:
            try:
                acc_7d  = await _get_recent_accuracy(db, ticker, days=7)
                acc_30d = await _get_recent_accuracy(db, ticker, days=30)

                # 샘플 수
                since = today - timedelta(days=30)
                stmt = select(StockPrediction).where(
                    StockPrediction.ticker == ticker,
                    StockPrediction.prediction_date >= since,
                    StockPrediction.was_correct.is_not(None),
                )
                rows = (await db.execute(stmt)).scalars().all()

                retrain = False
                if acc_30d is not None:
                    retrain = should_retrain(ticker, acc_30d)

                row = MLModelPerformance(
                    ticker=ticker,
                    eval_date=today,
                    accuracy_7d=acc_7d,
                    accuracy_30d=acc_30d,
                    sample_count=len(rows),
                    retrain_triggered=retrain,
                )
                db.add(row)
            except Exception as e:
                logger.warning(f"[성과기록] {ticker} 실패: {e}")

        await db.commit()
    logger.info("모델 성과 기록 완료")


# ── 메인 ─────────────────────────────────────────────────────────────────

async def run_weekly_full_retrain(loop: asyncio.AbstractEventLoop):
    """
    주간 풀 재학습 (Optuna 튜닝 포함)
    - 모든 종목 강제 재학습 (should_retrain 조건 무시)
    - Walk-forward 검증 결과도 성과 테이블에 저장
    """
    from core.feature_engineer import build_feature_matrix, create_labels
    from core.ml_predictor import train, predict, walk_forward_validation, get_model_meta

    logger.info(f"── 주간 풀 재학습 시작: {len(TICKERS)}개 종목")
    results = []

    for ticker in TICKERS:
        logger.info(f"[{ticker}] 주간 재학습 시작")
        try:
            features = await loop.run_in_executor(
                None, build_feature_matrix, ticker, DAYS_BACK, True
            )
            if features.empty or len(features) < 100:
                logger.warning(f"[{ticker}] 데이터 부족, 스킵")
                results.append({"ticker": ticker, "status": "skip"})
                continue

            labels = create_labels(features["close"], horizon=1)

            # Walk-forward 검증 먼저 수행 (재학습 전 베이스라인 측정)
            wf_result = await loop.run_in_executor(
                None, walk_forward_validation, features, labels
            )
            logger.info(
                f"[{ticker}] Walk-forward: mean_acc={wf_result.get('wf_accuracy', 0):.4f}, "
                f"periods={wf_result.get('n_periods', 0)}"
            )

            # 강제 재학습 (use_optuna=True)
            train_result = await loop.run_in_executor(
                None, train, ticker, features, labels, True
            )

            # Walk-forward 결과를 성과 테이블에 저장
            today = date.today()
            async with SessionLocal() as db:
                row = MLModelPerformance(
                    ticker=ticker,
                    eval_date=today,
                    accuracy_7d=None,
                    accuracy_30d=wf_result.get("wf_accuracy"),
                    sample_count=wf_result.get("n_periods", 0),
                    retrain_triggered=True,
                )
                db.add(row)
                await db.commit()

            logger.info(
                f"[{ticker}] 주간 재학습 완료: cv_acc={train_result['cv_accuracy']:.4f}"
            )
            results.append({"ticker": ticker, "status": "ok", **train_result})

        except Exception as e:
            logger.error(f"[{ticker}] 주간 재학습 실패: {e}", exc_info=True)
            results.append({"ticker": ticker, "status": "error", "reason": str(e)})

        await asyncio.sleep(3)

    ok    = [r for r in results if r["status"] == "ok"]
    error = [r for r in results if r["status"] == "error"]
    logger.info(f"주간 재학습 완료: {len(ok)}성공 / {len(error)}실패")


async def main():
    logger.info("=" * 60)
    logger.info(f"ML 트레이너 시작 | 모드={RUN_MODE} | {datetime.now().isoformat()}")
    logger.info(f"대상 종목: {len(TICKERS)}개 | 학습기간: {DAYS_BACK}일")
    logger.info("=" * 60)

    # ── 공휴일/주말 체크 (verify 제외: 검증은 전날 거래 여부 확인) ────────
    if RUN_MODE != "verify":
        today = date.today()
        if not _is_kr_trading_day(today):
            logger.info(f"오늘({today})은 한국 주식 휴장일입니다. 실행을 건너뜁니다.")
            return

    await _ensure_tables()

    loop = asyncio.get_event_loop()

    # ── verify 모드: 전일 예측 검증 + 성과 기록만 ───────────────────────
    if RUN_MODE == "verify":
        logger.info("── 검증 모드")
        await verify_yesterday_predictions()
        await record_model_performance()
        return

    # ── weekly 모드: Optuna 포함 풀 재학습 ──────────────────────────────
    if RUN_MODE == "weekly":
        logger.info("── 주간 풀 재학습 모드")
        await verify_yesterday_predictions()
        await record_model_performance()
        await run_weekly_full_retrain(loop)
        return

    # ── daily 모드 (기본): 조건부 재학습 + 예측 ─────────────────────────
    # 1. 전일 예측 검증
    logger.info("── STEP 1: 전일 예측 검증")
    await verify_yesterday_predictions()

    # 2. 성과 기록
    logger.info("── STEP 2: 모델 성과 기록")
    await record_model_performance()

    # 3. 학습 + 예측 (순차 처리, API Rate Limit 방지)
    logger.info(f"── STEP 3: {len(TICKERS)}개 종목 학습/예측")
    results = []
    for ticker in TICKERS:
        result = await process_ticker(ticker, loop)
        results.append(result)
        # 과도한 API 호출 방지
        await asyncio.sleep(2)

    # 요약 출력
    ok    = [r for r in results if r["status"] == "ok"]
    skip  = [r for r in results if r["status"] == "skip"]
    error = [r for r in results if r["status"] == "error"]

    logger.info("=" * 60)
    logger.info(f"완료: {len(ok)}성공 / {len(skip)}스킵 / {len(error)}실패")
    for r in ok:
        logger.info(f"  {r['ticker']}: {r['direction']} (상승확률={r.get('up_prob')}%, acc={r.get('cv_accuracy', 0):.3f})")
    for r in error:
        logger.warning(f"  {r['ticker']}: {r.get('reason', 'unknown')}")
    logger.info("=" * 60)


# 공유 모델 임포트 (DB에 저장하기 위해)
try:
    import sys
    sys.path.insert(0, "/app")
    from db.models import StockPrediction, MLModelPerformance  # type: ignore
except ImportError:
    # 직접 정의 (standalone 실행 시)
    from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
    from sqlalchemy import Integer, String, Float, Date, DateTime, Boolean, JSON, Index, func
    from datetime import date as _date
    from typing import Optional as _Optional

    class _Base(DeclarativeBase):
        pass

    class StockPrediction(_Base):  # type: ignore
        __tablename__ = "stock_predictions"
        __table_args__ = (
            Index("idx_pred_ticker_date", "ticker", "prediction_date"),
        )
        id:               Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
        ticker:           Mapped[str]             = mapped_column(String(20))
        prediction_date:  Mapped[_date]           = mapped_column(Date)
        predicted_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
        direction:        Mapped[str]             = mapped_column(String(10))
        up_prob:          Mapped[float]           = mapped_column(Float)
        confidence:       Mapped[float]           = mapped_column(Float)
        cv_accuracy:      Mapped[_Optional[float]] = mapped_column(Float)
        shap_top5:        Mapped[_Optional[dict]] = mapped_column(JSON)
        model_version:    Mapped[_Optional[str]]  = mapped_column(String(50))
        actual_direction: Mapped[_Optional[str]]  = mapped_column(String(10))
        actual_return:    Mapped[_Optional[float]] = mapped_column(Float)
        was_correct:      Mapped[_Optional[bool]] = mapped_column(Boolean)

    class MLModelPerformance(_Base):  # type: ignore
        __tablename__ = "ml_model_performance"
        id:                Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
        ticker:            Mapped[str]             = mapped_column(String(20))
        eval_date:         Mapped[_date]           = mapped_column(Date)
        accuracy_7d:       Mapped[_Optional[float]] = mapped_column(Float)
        accuracy_30d:      Mapped[_Optional[float]] = mapped_column(Float)
        sample_count:      Mapped[int]             = mapped_column(Integer, default=0)
        retrain_triggered: Mapped[bool]            = mapped_column(Boolean, default=False)
        created_at:        Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())


if __name__ == "__main__":
    asyncio.run(main())
