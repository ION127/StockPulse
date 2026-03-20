"""POST /api/v1/analyze/trigger 라우터"""

import asyncio
import uuid
import logging
import os
from datetime import datetime
from typing import Callable, Awaitable
from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.connection import AsyncSessionLocal
from db.models import Anomaly, AnalysisResult
from schemas.anomaly import JobResponse
from services.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analyze", tags=["Jobs"])

_jobs: dict[str, dict] = {}

# main.py에서 앱 시작 시 set_broadcast()로 주입 (순환 임포트 방지)
_broadcast: Callable[[dict], Awaitable[None]] | None = None


def set_broadcast(fn: Callable[[dict], Awaitable[None]]) -> None:
    global _broadcast
    _broadcast = fn


async def _noop_broadcast(_: dict) -> None:
    pass


@router.post("/trigger", response_model=JobResponse)
async def trigger_analysis(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"job_id": job_id, "status": "queued",
                     "started_at": None, "completed_at": None,
                     "anomaly_count": None, "message": None}
    background_tasks.add_task(_run_job, job_id)
    return JobResponse(**_jobs[job_id])


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없음")
    return JobResponse(**_jobs[job_id])


async def _run_job(job_id: str):
    broadcast = _broadcast or _noop_broadcast
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now()
    try:
        async with AsyncSessionLocal() as db:
            result = await run_pipeline(db=db, broadcast=broadcast)
        _jobs[job_id].update({"status": "done", "completed_at": datetime.now(),
                               "anomaly_count": result.get("anomaly_count", 0),
                               "message": f"완료: {result.get('analyzed_count', 0)}개 분석"})
    except Exception as e:
        _jobs[job_id].update({"status": "failed", "completed_at": datetime.now(), "message": str(e)})
        logger.error(f"잡 실패 {job_id}: {e}")


# ── 과거 이상값 재분석 ─────────────────────────────────────────────────────────

@router.post("/reanalyze", response_model=JobResponse)
async def reanalyze_truncated(background_tasks: BackgroundTasks, days: int = 7, min_length: int = 200):
    """분석이 없거나 잘린 이상값을 찾아 뉴스 수집 후 재분석.

    - days: 최근 며칠 이내 이상값 대상 (기본 7일)
    - min_length: 이 글자수 미만이면 잘린 것으로 판단 (기본 200자)
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"job_id": job_id, "status": "queued",
                     "started_at": None, "completed_at": None,
                     "anomaly_count": None, "message": None}
    background_tasks.add_task(_run_reanalyze_job, job_id, days, min_length)
    return JobResponse(**_jobs[job_id])


async def _run_reanalyze_job(job_id: str, days: int, min_length: int):
    from datetime import date, timedelta
    from core.ai_analyzer import analyze_anomaly
    from core.news_fetcher import fetch_news_for_anomaly, format_news_for_prompt
    from core.stock_categories import STOCK_CATEGORIES

    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now()
    loop = asyncio.get_event_loop()

    try:
        since = date.today() - timedelta(days=days)
        fixed = 0

        async with AsyncSessionLocal() as db:
            stmt = (
                select(Anomaly)
                .options(selectinload(Anomaly.analysis))
                .where(Anomaly.anomaly_date >= since)
            )
            anomalies = (await db.execute(stmt)).scalars().all()

            targets = [
                a for a in anomalies
                if a.analysis is None
                or len(a.analysis.analysis_ko or "") < min_length
                or (a.analysis.analysis_ko or "").startswith("분석 실패")
                or (a.analysis.analysis_ko or "").startswith("Analysis failed")
            ]

            logger.info(f"[reanalyze] 대상 {len(targets)}건 (전체 {len(anomalies)}건 중, 최근 {days}일)")

            for anomaly in targets:
                try:
                    # 뉴스 수집 (실패해도 빈 텍스트로 계속 진행)
                    sector = anomaly.sector or ""
                    cat_data = STOCK_CATEGORIES.get(sector, {})
                    try:
                        news_data = await loop.run_in_executor(
                            None, fetch_news_for_anomaly,
                            anomaly.ticker, sector,
                            cat_data.get("keywords_en", [anomaly.ticker.replace("KR:", "")]),
                            cat_data.get("keywords_kr", []),
                        )
                        news_text = format_news_for_prompt(news_data)
                        news_en = news_data.get("en", [])
                        news_kr = news_data.get("kr", [])
                    except Exception as ne:
                        logger.warning(f"[reanalyze] 뉴스 수집 실패 ({anomaly.ticker}): {ne}")
                        news_text = ""
                        news_en = []
                        news_kr = []

                    # AI 분석 (별도 스레드에서 실행 — time.sleep 포함된 동기 함수)
                    result = await loop.run_in_executor(
                        None, analyze_anomaly,
                        anomaly.ticker, sector, anomaly.return_pct, anomaly.direction,
                        str(anomaly.anomaly_date), float(anomaly.close_price or 0),
                        news_text, anomaly.event_type,
                        int(anomaly.sector_peer_count or 1),
                        int(anomaly.moving_sector_count or 1),
                    )

                    if anomaly.analysis:
                        # 기존 분석 업데이트
                        anomaly.analysis.analysis_ko = result.get("ko", "")
                        anomaly.analysis.analysis_en = result.get("en", "")
                        if news_en:
                            anomaly.analysis.news_en = news_en
                        if news_kr:
                            anomaly.analysis.news_kr = news_kr
                    else:
                        # 새 분석 생성
                        db.add(AnalysisResult(
                            anomaly_id=anomaly.id,
                            analysis_ko=result.get("ko", ""),
                            analysis_en=result.get("en", ""),
                            news_en=news_en,
                            news_kr=news_kr,
                        ))

                    await db.commit()
                    fixed += 1
                    logger.info(f"[reanalyze] 완료: {anomaly.ticker} (#{anomaly.id})")

                except Exception as e:
                    logger.error(f"[reanalyze] 실패: {anomaly.ticker} — {e}")

        _jobs[job_id].update({
            "status": "done",
            "completed_at": datetime.now(),
            "anomaly_count": fixed,
            "message": f"재분석 완료: {fixed}/{len(targets)}건",
        })

    except Exception as e:
        _jobs[job_id].update({"status": "failed", "completed_at": datetime.now(), "message": str(e)})
        logger.error(f"재분석 잡 실패 {job_id}: {e}")
