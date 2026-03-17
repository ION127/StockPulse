"""Pydantic 스키마 - API 요청/응답 타입 정의"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class AnomalyBase(BaseModel):
    ticker: str
    anomaly_date: date
    return_pct: float
    zscore: Optional[float] = None
    close_price: Optional[float] = None
    volume: Optional[int] = None
    direction: str           # "급등" or "급락"
    event_type: str          # "INDIVIDUAL", "SECTOR", "MARKET"
    sector: Optional[str] = None
    sector_peer_count: Optional[int] = None
    moving_sector_count: Optional[int] = None


class AnomalyResponse(AnomalyBase):
    id: int
    detected_at: datetime
    has_analysis: bool = False

    class Config:
        from_attributes = True


class NewsArticle(BaseModel):
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    source: Optional[str] = None
    language: str  # "en" or "kr"


class AnalysisResponse(BaseModel):
    id: int
    anomaly_id: int
    created_at: datetime
    analysis_ko: str
    analysis_en: str
    news_en: list[NewsArticle] = []
    news_kr: list[NewsArticle] = []

    class Config:
        from_attributes = True


class SectorTrendItem(BaseModel):
    sector: str
    anomaly_count: int
    avg_return_pct: float
    up_count: int
    down_count: int
    hot_tickers: list[str]


class JobResponse(BaseModel):
    job_id: str
    status: str              # "queued", "running", "done", "failed"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    anomaly_count: Optional[int] = None
    message: Optional[str] = None
