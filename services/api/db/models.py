"""SQLAlchemy ORM 모델"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import Integer, String, Float, Date, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.connection import Base


class Anomaly(Base):
    __tablename__ = "anomalies"

    id:                  Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at:         Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
    ticker:              Mapped[str]             = mapped_column(String(20), nullable=False, index=True)
    anomaly_date:        Mapped[date]            = mapped_column(Date, nullable=False, index=True)
    return_pct:          Mapped[float]           = mapped_column(Float, nullable=False)
    zscore:              Mapped[Optional[float]] = mapped_column(Float)
    close_price:         Mapped[Optional[float]] = mapped_column(Float)
    volume:              Mapped[Optional[int]]   = mapped_column(Integer)
    direction:           Mapped[str]             = mapped_column(String(10))
    event_type:          Mapped[str]             = mapped_column(String(20))
    sector:              Mapped[Optional[str]]   = mapped_column(String(100), index=True)
    sector_peer_count:   Mapped[Optional[int]]   = mapped_column(Integer)
    moving_sector_count: Mapped[Optional[int]]   = mapped_column(Integer)

    analysis: Mapped[Optional["AnalysisResult"]] = relationship(back_populates="anomaly", uselist=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    anomaly_id:  Mapped[int]      = mapped_column(Integer, ForeignKey("anomalies.id"), unique=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    analysis_ko: Mapped[str]      = mapped_column(Text)
    analysis_en: Mapped[str]      = mapped_column(Text)
    news_en:     Mapped[list]     = mapped_column(JSON, default=list)
    news_kr:     Mapped[list]     = mapped_column(JSON, default=list)

    anomaly: Mapped["Anomaly"] = relationship(back_populates="analysis")
