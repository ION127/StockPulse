"""DB 쿼리 레포지토리"""

from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy import select, func, desc, text, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Anomaly, AnalysisResult, SignalPerformance


class AnomalyRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_anomaly(self, data: dict) -> Anomaly:
        stmt = (
            select(Anomaly)
            .options(selectinload(Anomaly.analysis))
            .where(
                Anomaly.ticker == data["ticker"],
                Anomaly.anomaly_date == data["anomaly_date"],
            )
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        anomaly = Anomaly(**data)
        self.db.add(anomaly)
        await self.db.commit()
        await self.db.refresh(anomaly)
        return anomaly

    async def save_analysis(self, anomaly_id: int, analysis_ko: str, analysis_en: str,
                            news_en: list, news_kr: list) -> AnalysisResult:
        result = AnalysisResult(
            anomaly_id=anomaly_id,
            analysis_ko=analysis_ko,
            analysis_en=analysis_en,
            news_en=news_en,
            news_kr=news_kr,
        )
        self.db.add(result)
        await self.db.commit()
        await self.db.refresh(result)
        return result

    async def get_recent_anomalies(self, days: int = 7, sector: Optional[str] = None,
                                   event_type: Optional[str] = None, limit: int = 50) -> list[Anomaly]:
        since = date.today() - timedelta(days=days)
        stmt = (
            select(Anomaly)
            .options(selectinload(Anomaly.analysis))
            .where(Anomaly.anomaly_date >= since)
        )
        if sector:
            stmt = stmt.where(Anomaly.sector == sector)
        if event_type:
            stmt = stmt.where(Anomaly.event_type == event_type)
        stmt = stmt.order_by(desc(Anomaly.anomaly_date), desc(func.abs(Anomaly.return_pct))).limit(limit)
        return (await self.db.execute(stmt)).scalars().all()

    async def get_ticker_history(self, ticker: str, days: int = 30) -> list[Anomaly]:
        since = date.today() - timedelta(days=days)
        stmt = (
            select(Anomaly)
            .options(selectinload(Anomaly.analysis))
            .where(Anomaly.ticker == ticker, Anomaly.anomaly_date >= since)
            .order_by(desc(Anomaly.anomaly_date))
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_analysis(self, anomaly_id: int) -> Optional[AnalysisResult]:
        stmt = select(AnalysisResult).where(AnalysisResult.anomaly_id == anomaly_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── Signal Performance ────────────────────────────────────────────────

    async def create_signal_performance(
        self,
        anomaly_id: int,
        ticker: str,
        direction: str,
        detected_price: Optional[float],
        detected_at: datetime,
    ) -> SignalPerformance:
        """이상감지 직후 성과 추적 레코드 생성."""
        sp = SignalPerformance(
            anomaly_id=anomaly_id,
            ticker=ticker,
            direction=direction,
            detected_price=detected_price,
            measure_1h_at=detected_at + timedelta(hours=1),
            measure_24h_at=detected_at + timedelta(hours=24),
            measure_1w_at=detected_at + timedelta(days=7),
        )
        self.db.add(sp)
        await self.db.commit()
        await self.db.refresh(sp)
        return sp

    async def get_pending_measurements(self, now: datetime) -> list[SignalPerformance]:
        """
        아직 측정되지 않은(NULL) 항목 중 측정 시각이 된 레코드 반환.
        1h / 24h / 1w 중 하나라도 측정 대기 중인 것.
        """
        stmt = select(SignalPerformance).where(
            and_(
                SignalPerformance.detected_price.isnot(None),
                (
                    and_(SignalPerformance.measure_1h_at <= now,  SignalPerformance.price_1h.is_(None))
                    | and_(SignalPerformance.measure_24h_at <= now, SignalPerformance.price_24h.is_(None))
                    | and_(SignalPerformance.measure_1w_at <= now,  SignalPerformance.price_1w.is_(None))
                ),
            )
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def update_signal_measurement(
        self,
        sp_id: int,
        field_price: str,
        field_return: str,
        price: float,
        detected_price: float,
    ) -> None:
        """단일 측정 포인트(1h / 24h / 1w) 업데이트."""
        return_pct = ((price - detected_price) / detected_price) * 100 if detected_price else None
        stmt = select(SignalPerformance).where(SignalPerformance.id == sp_id)
        sp = (await self.db.execute(stmt)).scalar_one_or_none()
        if sp:
            setattr(sp, field_price, price)
            setattr(sp, field_return, return_pct)
            await self.db.commit()

    async def get_performance_summary(self, days: int = 30) -> dict:
        """전체 시그널 적중률 통계 반환."""
        since = datetime.utcnow() - timedelta(days=days)
        sql = text("""
            SELECT
                COUNT(*)                                                  AS total,
                COUNT(price_1h)                                           AS measured_1h,
                COUNT(price_24h)                                          AS measured_24h,
                COUNT(price_1w)                                           AS measured_1w,
                AVG(return_1h)                                            AS avg_return_1h,
                AVG(return_24h)                                           AS avg_return_24h,
                AVG(return_1w)                                            AS avg_return_1w,
                SUM(CASE WHEN direction = '급등' AND return_24h > 0 THEN 1
                         WHEN direction = '급락' AND return_24h < 0 THEN 1
                         ELSE 0 END)                                      AS correct_24h,
                COUNT(return_24h)                                         AS total_measured_24h
            FROM signal_performance
            WHERE created_at >= :since
        """)
        row = (await self.db.execute(sql, {"since": since})).mappings().one()
        accuracy_24h = None
        if row["total_measured_24h"]:
            accuracy_24h = round(row["correct_24h"] / row["total_measured_24h"] * 100, 1)
        return {
            "period_days":      days,
            "total":            row["total"],
            "measured_24h":     row["measured_24h"],
            "avg_return_1h":    round(row["avg_return_1h"] or 0, 2),
            "avg_return_24h":   round(row["avg_return_24h"] or 0, 2),
            "avg_return_1w":    round(row["avg_return_1w"] or 0, 2),
            "accuracy_24h_pct": accuracy_24h,
        }

    async def get_ticker_performance(self, ticker: str, days: int = 90) -> list[SignalPerformance]:
        """종목별 시그널 성과 이력 반환."""
        since = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(SignalPerformance)
            .where(
                SignalPerformance.ticker == ticker,
                SignalPerformance.created_at >= since,
            )
            .order_by(desc(SignalPerformance.created_at))
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_sector_trends(self, days: int = 7) -> list[dict]:
        since = date.today() - timedelta(days=days)
        sql = text("""
            SELECT sector,
                   COUNT(*) AS anomaly_count,
                   AVG(return_pct) AS avg_return_pct,
                   SUM(CASE WHEN direction = '급등' THEN 1 ELSE 0 END) AS up_count,
                   SUM(CASE WHEN direction = '급락' THEN 1 ELSE 0 END) AS down_count
            FROM anomalies
            WHERE anomaly_date >= :since AND sector IS NOT NULL
            GROUP BY sector
            ORDER BY anomaly_count DESC
        """)
        rows = (await self.db.execute(sql, {"since": since})).mappings().all()

        trends = []
        for row in rows:
            ticker_sql = text("""
                SELECT ticker FROM anomalies
                WHERE anomaly_date >= :since AND sector = :sector
                ORDER BY ABS(return_pct) DESC LIMIT 3
            """)
            hot_tickers = [r[0] for r in (await self.db.execute(
                ticker_sql, {"since": since, "sector": row["sector"]}
            )).fetchall()]
            trends.append({**dict(row), "hot_tickers": hot_tickers})
        return trends
