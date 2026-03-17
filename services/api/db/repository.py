"""DB 쿼리 레포지토리"""

from datetime import date, timedelta
from typing import Optional
from sqlalchemy import select, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Anomaly, AnalysisResult


class AnomalyRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_anomaly(self, data: dict) -> Anomaly:
        stmt = select(Anomaly).where(
            Anomaly.ticker == data["ticker"],
            Anomaly.anomaly_date == data["anomaly_date"],
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
