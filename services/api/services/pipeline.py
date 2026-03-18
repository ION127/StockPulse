"""분석 파이프라인 서비스 - core 모듈을 FastAPI 비동기로 실행"""

import asyncio
import logging
from datetime import datetime
from typing import Callable
from sqlalchemy.ext.asyncio import AsyncSession

from core.stock_categories import STOCK_CATEGORIES, get_all_us_tickers, get_all_kr_tickers
from core.stock_fetcher import fetch_us_stocks, fetch_kr_stocks, detect_anomalies, \
    get_sector_anomaly_summary, classify_event_type
from core.news_fetcher import fetch_news_for_anomaly, format_news_for_prompt
from core.ai_analyzer import analyze_anomaly, analyze_sector_trends
from db.repository import AnomalyRepository

logger = logging.getLogger(__name__)


async def run_pipeline(db: AsyncSession, broadcast: Callable,
                       threshold_pct: float = 3.0, threshold_z: float = 2.0,
                       kr_threshold_pct: float = 4.0) -> dict:
    repo = AnomalyRepository(db)
    result_summary = {"anomaly_count": 0, "analyzed_count": 0}
    loop = asyncio.get_event_loop()

    # 1. 주가 수집
    us_data, kr_data = await asyncio.gather(
        loop.run_in_executor(None, fetch_us_stocks, get_all_us_tickers()),
        loop.run_in_executor(None, fetch_kr_stocks, get_all_kr_tickers()),
    )
    logger.info(f"수집 완료: 미국 {len(us_data)}개, 한국 {len(kr_data)}개")

    # 2. 이상값 탐지
    all_anomalies = await loop.run_in_executor(
        None, detect_anomalies, {**us_data, **kr_data},
        threshold_pct, threshold_z, 20, kr_threshold_pct
    )
    recent = [a for a in all_anomalies if a.get("is_recent")]
    if not recent:
        return result_summary

    # 3. 섹터 분류
    classified = classify_event_type(recent, STOCK_CATEGORIES)
    result_summary["anomaly_count"] = len(classified)

    # 4. DB 저장 + WebSocket 브로드캐스트
    saved_anomalies = []
    for anomaly in classified:
        saved = await repo.save_anomaly({
            "ticker": anomaly["ticker"], "anomaly_date": anomaly["date"],
            "return_pct": anomaly["return_pct"], "zscore": anomaly.get("zscore"),
            "close_price": anomaly.get("close_price"), "volume": anomaly.get("volume"),
            "direction": anomaly["direction"], "event_type": anomaly.get("event_type", "INDIVIDUAL"),
            "sector": anomaly.get("sector"), "sector_peer_count": anomaly.get("sector_peer_count"),
            "moving_sector_count": anomaly.get("moving_sector_count"),
        })
        saved_anomalies.append((saved, anomaly))
        await broadcast({"type": "anomaly", "ticker": anomaly["ticker"],
                         "return_pct": anomaly["return_pct"], "direction": anomaly["direction"],
                         "sector": anomaly.get("sector", ""), "event_type": anomaly.get("event_type", "INDIVIDUAL")})

    # 5. 뉴스 + AI 분석 (최대 5개)
    analyzed = 0
    for saved_anomaly, raw in saved_anomalies[:5]:
        if saved_anomaly.analysis:
            continue
        sector = raw.get("sector", "")
        cat_data = STOCK_CATEGORIES.get(sector, {})
        news_data = await loop.run_in_executor(
            None, fetch_news_for_anomaly, raw["ticker"], sector,
            cat_data.get("keywords_en", [raw["ticker"]]), cat_data.get("keywords_kr", []),
        )
        analysis = await loop.run_in_executor(
            None, analyze_anomaly, raw["ticker"], sector, raw["return_pct"], raw["direction"],
            str(raw["date"]), raw.get("close_price", 0), format_news_for_prompt(news_data),
            raw.get("event_type", "INDIVIDUAL"), raw.get("sector_peer_count", 1),
            raw.get("moving_sector_count", 1),
        )
        await repo.save_analysis(saved_anomaly.id, analysis["ko"], analysis["en"],
                                 news_data.get("en", []), news_data.get("kr", []))
        analyzed += 1

    result_summary["analyzed_count"] = analyzed
    result_summary["completed_at"] = datetime.now().isoformat()
    return result_summary
