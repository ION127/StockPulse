"""
시그널 성과 추적기 — 이상감지 후 1h / 24h / 7d 가격 자동 측정

동작 방식:
  - APScheduler에 의해 5분마다 실행
  - signal_performance 테이블에서 측정 대기 중인 레코드 조회
  - yfinance로 해당 시점 가격 조회 → return_pct 계산 후 업데이트
"""

import logging
from datetime import datetime

import yfinance as yf

from db.connection import AsyncSessionLocal
from db.repository import AnomalyRepository

logger = logging.getLogger(__name__)

# 측정 포인트 정의: (측정 예정 시각 컬럼, 가격 컬럼, 수익률 컬럼)
_MEASUREMENT_POINTS = [
    ("measure_1h_at",  "price_1h",  "return_1h"),
    ("measure_24h_at", "price_24h", "return_24h"),
    ("measure_1w_at",  "price_1w",  "return_1w"),
]


def _to_yfinance_ticker(ticker: str) -> str:
    """
    내부 ticker 형식 → yfinance 형식 변환.
    예: 'KR:005930' → '005930.KS',  'NVDA' → 'NVDA'
    """
    if ticker.startswith("KR:"):
        code = ticker[3:]
        return f"{code}.KS"
    return ticker


def _fetch_current_price(ticker: str) -> float | None:
    """yfinance로 현재가(또는 최근 종가) 조회. 실패 시 None 반환."""
    yf_ticker = _to_yfinance_ticker(ticker)
    try:
        info = yf.Ticker(yf_ticker).fast_info
        price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        return float(price) if price else None
    except Exception as e:
        logger.debug(f"가격 조회 실패 [{ticker}({yf_ticker})]: {e}")
        return None


async def run_performance_check() -> None:
    """
    APScheduler에서 호출되는 진입점.
    측정 대기 레코드를 처리하고 결과를 DB에 저장.
    """
    now = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        repo = AnomalyRepository(db)
        pending = await repo.get_pending_measurements(now)

        if not pending:
            return

        logger.info(f"[성과추적] 측정 대기 {len(pending)}건 처리 시작")
        updated = 0

        for sp in pending:
            if sp.detected_price is None:
                continue

            for measure_at_field, price_field, return_field in _MEASUREMENT_POINTS:
                # 이미 측정됐으면 skip
                if getattr(sp, price_field) is not None:
                    continue
                # 측정 시각이 아직 안 됐으면 skip
                measure_at: datetime = getattr(sp, measure_at_field)
                if measure_at > now:
                    continue

                price = _fetch_current_price(sp.ticker)
                if price is None:
                    logger.warning(f"[성과추적] {sp.ticker} 가격 조회 실패 — 다음 주기에 재시도")
                    continue

                await repo.update_signal_measurement(
                    sp_id=sp.id,
                    field_price=price_field,
                    field_return=return_field,
                    price=price,
                    detected_price=sp.detected_price,
                )
                updated += 1
                logger.debug(
                    f"[성과추적] {sp.ticker} {price_field}={price:.2f} "
                    f"(기준가={sp.detected_price:.2f})"
                )

        if updated:
            logger.info(f"[성과추적] {updated}건 측정 완료")
