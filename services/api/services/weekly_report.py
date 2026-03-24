"""
주간/월간 이상감지 패턴 리포트 생성 + Slack 발송

APScheduler에 의해 매주 월요일 09:00 KST에 자동 실행.
SLACK_WEBHOOK_URL 환경변수가 설정된 경우에만 발송.

리포트 내용:
  - 기간 내 이상감지 총 건수
  - 가장 활발했던 섹터 TOP 3
  - 가장 많이 감지된 종목 TOP 5
  - 급등/급락 비율
  - 시그널 성과 요약 (데이터가 있을 경우)
"""

import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")

import requests

from db.connection import AsyncSessionLocal
from db.repository import AnomalyRepository

logger = logging.getLogger(__name__)

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")


def _send_slack(text: str) -> None:
    if not SLACK_WEBHOOK:
        logger.info(f"[주간리포트 — Slack 미설정, 로그 출력]\n{text}")
        return
    try:
        resp = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
        resp.raise_for_status()
        logger.info("[주간리포트] Slack 발송 완료")
    except Exception as e:
        logger.error(f"[주간리포트] Slack 발송 실패: {e}")


def _format_report(stats: dict, period_label: str) -> str:
    """리포트 데이터를 Slack 메시지 형식으로 변환."""
    lines = [
        f"📊 *StockPulse {period_label} 리포트*",
        f"📅 {stats['since']} ~ {stats['until']}",
        "",
        f"🔔 *총 이상감지:* {stats['total_anomalies']}건",
        f"   📈 급등: {stats['up_count']}건 | 📉 급락: {stats['down_count']}건",
        "",
    ]

    if stats["top_sectors"]:
        lines.append("🏭 *핫 섹터 TOP 3:*")
        for i, s in enumerate(stats["top_sectors"][:3], 1):
            lines.append(f"   {i}. {s['sector']} — {s['count']}건 (평균 {s['avg_return']:+.1f}%)")
        lines.append("")

    if stats["top_tickers"]:
        lines.append("📌 *많이 감지된 종목 TOP 5:*")
        for i, t in enumerate(stats["top_tickers"][:5], 1):
            lines.append(f"   {i}. {t['ticker']} — {t['count']}건")
        lines.append("")

    if stats.get("signal_accuracy") is not None:
        lines.append(f"🎯 *시그널 적중률 (24h 기준):* {stats['signal_accuracy']}%")
        lines.append("")

    lines.append("_StockPulse 자동 리포트_")
    return "\n".join(lines)


async def _gather_stats(days: int) -> dict:
    """DB에서 기간별 통계 수집."""
    today_kst = datetime.now(_KST).date()
    since = today_kst - timedelta(days=days)
    until = today_kst

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, func, desc, text
        from db.models import Anomaly

        # 총 건수 + 급등/급락
        total_sql = text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN direction = '급등' THEN 1 ELSE 0 END) AS up_count,
                SUM(CASE WHEN direction = '급락' THEN 1 ELSE 0 END) AS down_count
            FROM anomalies
            WHERE anomaly_date >= :since
        """)
        row = (await db.execute(total_sql, {"since": since})).mappings().one()
        total = int(row["total"] or 0)
        up_count = int(row["up_count"] or 0)
        down_count = int(row["down_count"] or 0)

        # 섹터별 집계
        sector_sql = text("""
            SELECT sector, COUNT(*) AS cnt, AVG(return_pct) AS avg_ret
            FROM anomalies
            WHERE anomaly_date >= :since AND sector IS NOT NULL
            GROUP BY sector
            ORDER BY cnt DESC
            LIMIT 3
        """)
        top_sectors = [
            {"sector": r["sector"], "count": int(r["cnt"]), "avg_return": float(r["avg_ret"] or 0)}
            for r in (await db.execute(sector_sql, {"since": since})).mappings().all()
        ]

        # 종목별 집계
        ticker_sql = text("""
            SELECT ticker, COUNT(*) AS cnt
            FROM anomalies
            WHERE anomaly_date >= :since
            GROUP BY ticker
            ORDER BY cnt DESC
            LIMIT 5
        """)
        top_tickers = [
            {"ticker": r["ticker"], "count": int(r["cnt"])}
            for r in (await db.execute(ticker_sql, {"since": since})).mappings().all()
        ]

        # 시그널 적중률 (signal_performance 테이블)
        accuracy = None
        try:
            repo = AnomalyRepository(db)
            perf = await repo.get_performance_summary(days=days)
            accuracy = perf.get("accuracy_24h_pct")
        except Exception:
            pass

    return {
        "since":            str(since),
        "until":            str(until),
        "total_anomalies":  total,
        "up_count":         up_count,
        "down_count":       down_count,
        "top_sectors":      top_sectors,
        "top_tickers":      top_tickers,
        "signal_accuracy":  accuracy,
    }


async def run_weekly_report() -> None:
    """매주 월요일 실행 — 지난 7일 통계 리포트."""
    logger.info("[주간리포트] 생성 시작")
    try:
        stats = await _gather_stats(days=7)
        if stats["total_anomalies"] == 0:
            logger.info("[주간리포트] 지난 7일 이상감지 없음 — 발송 생략")
            return
        text = _format_report(stats, "주간")
        _send_slack(text)
    except Exception as e:
        logger.error(f"[주간리포트] 오류: {e}", exc_info=True)


async def run_monthly_report() -> None:
    """매월 1일 실행 — 지난 30일 통계 리포트."""
    logger.info("[월간리포트] 생성 시작")
    try:
        stats = await _gather_stats(days=30)
        if stats["total_anomalies"] == 0:
            logger.info("[월간리포트] 지난 30일 이상감지 없음 — 발송 생략")
            return
        text = _format_report(stats, "월간")
        _send_slack(text)
    except Exception as e:
        logger.error(f"[월간리포트] 오류: {e}", exc_info=True)
