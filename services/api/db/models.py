"""SQLAlchemy ORM 모델"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import BigInteger, Boolean, Index, Integer, String, Float, Date, DateTime, Text, JSON, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.connection import Base



class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        Index("idx_anomaly_date_sector",    "anomaly_date", "sector"),
        Index("idx_anomaly_ticker_date",    "ticker",       "anomaly_date"),
        Index("idx_anomaly_date_direction", "anomaly_date", "direction"),
    )

    id:                  Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at:         Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
    ticker:              Mapped[str]             = mapped_column(String(20), nullable=False, index=True)
    anomaly_date:        Mapped[date]            = mapped_column(Date, nullable=False, index=True)
    bar_timestamp:       Mapped[Optional[str]]   = mapped_column(String(30))        # 1분봉 정확한 시각
    return_pct:          Mapped[float]           = mapped_column(Float, nullable=False)
    zscore:              Mapped[Optional[float]] = mapped_column(Float)
    close_price:         Mapped[Optional[float]] = mapped_column(Float)
    volume:              Mapped[Optional[int]]   = mapped_column(BigInteger)
    direction:           Mapped[str]             = mapped_column(String(10))
    is_etf:              Mapped[bool]            = mapped_column(Boolean, default=False)
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


# ── Phase 6: 사용자 인증 & 서버사이드 포트폴리오 ───────────────────────────

class User(Base):
    __tablename__ = "users"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    email:         Mapped[str]      = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str]      = mapped_column(String(255), nullable=False)
    tier:          Mapped[str]      = mapped_column(String(20), default="free")   # free/standard/pro/enterprise
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    watchlists:     Mapped[list["Watchlist"]]    = relationship(back_populates="user", cascade="all, delete-orphan")
    portfolios:     Mapped[list["Portfolio"]]    = relationship(back_populates="user", cascade="all, delete-orphan")
    alert_settings: Mapped[list["AlertSetting"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)

    id:       Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:  Mapped[int]      = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    ticker:   Mapped[str]      = mapped_column(String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="watchlists")


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_portfolio_user_ticker"),)

    id:        Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:   Mapped[int]      = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    ticker:    Mapped[str]      = mapped_column(String(20), nullable=False)
    quantity:  Mapped[float]    = mapped_column(Float, nullable=False)
    avg_price: Mapped[float]    = mapped_column(Float, nullable=False)
    added_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="portfolios")


class AlertSetting(Base):
    __tablename__ = "alert_settings"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_alert_user_ticker"),)

    id:             Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:        Mapped[int]      = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    ticker:         Mapped[str]      = mapped_column(String(20), nullable=False)
    threshold_pct:  Mapped[float]    = mapped_column(Float, default=3.0)
    alert_channel:  Mapped[str]      = mapped_column(String(20), default="email")  # email/kakao/browser
    quiet_start:    Mapped[Optional[int]] = mapped_column(Integer)  # 22 (22:00)
    quiet_end:      Mapped[Optional[int]] = mapped_column(Integer)  # 8  (08:00)

    user: Mapped["User"] = relationship(back_populates="alert_settings")


# ── Signal Performance Tracker ────────────────────────────────────────────────

class SignalPerformance(Base):
    """
    이상감지 시그널 성과 추적 테이블.
    anomaly 감지 후 1시간 / 24시간 / 7일 뒤 가격을 조회해 수익률을 기록.
    """
    __tablename__ = "signal_performance"
    __table_args__ = (
        Index("idx_sp_ticker",     "ticker"),
        Index("idx_sp_anomaly_id", "anomaly_id"),
    )

    id:             Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    anomaly_id:     Mapped[int]            = mapped_column(Integer, ForeignKey("anomalies.id"), unique=True)
    ticker:         Mapped[str]            = mapped_column(String(20), nullable=False)
    direction:      Mapped[str]            = mapped_column(String(10), nullable=False)   # '급등'/'급락'
    detected_price: Mapped[Optional[float]] = mapped_column(Float)

    # 측정 예정 시각 (스케줄러가 이 시각이 지나면 가격을 조회)
    measure_1h_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), index=True)
    measure_24h_at: Mapped[datetime]       = mapped_column(DateTime(timezone=True), index=True)
    measure_1w_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), index=True)

    # 측정 결과 (NULL = 아직 미측정)
    price_1h:       Mapped[Optional[float]] = mapped_column(Float)
    price_24h:      Mapped[Optional[float]] = mapped_column(Float)
    price_1w:       Mapped[Optional[float]] = mapped_column(Float)
    return_1h:      Mapped[Optional[float]] = mapped_column(Float)   # % 수익률
    return_24h:     Mapped[Optional[float]] = mapped_column(Float)
    return_1w:      Mapped[Optional[float]] = mapped_column(Float)

    created_at:     Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())

    anomaly: Mapped["Anomaly"] = relationship()


# ── ML 예측 ────────────────────────────────────────────────────────────────

class StockPrediction(Base):
    """ML 모델의 종목별 다음날 방향성 예측 결과"""
    __tablename__ = "stock_predictions"
    __table_args__ = (
        Index("idx_pred_ticker_date", "ticker", "prediction_date"),
        Index("idx_pred_date",        "prediction_date"),
    )

    id:               Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker:           Mapped[str]             = mapped_column(String(20), nullable=False)
    prediction_date:  Mapped[date]            = mapped_column(Date, nullable=False)  # 예측 대상 날짜
    predicted_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
    direction:        Mapped[str]             = mapped_column(String(10), nullable=False)  # 상승/하락
    up_prob:          Mapped[float]           = mapped_column(Float, nullable=False)       # 상승 확률 0-100
    confidence:       Mapped[float]           = mapped_column(Float)                       # 신뢰도 0-100
    cv_accuracy:      Mapped[Optional[float]] = mapped_column(Float)
    shap_top5:        Mapped[Optional[dict]]  = mapped_column(JSON)   # 상위 5 피처 기여도
    model_version:    Mapped[Optional[str]]   = mapped_column(String(50))

    # 사후 검증
    actual_direction: Mapped[Optional[str]]   = mapped_column(String(10))
    actual_return:    Mapped[Optional[float]] = mapped_column(Float)
    was_correct:      Mapped[Optional[bool]]  = mapped_column(Boolean)


class MLModelPerformance(Base):
    """ML 모델 롤링 정확도 추적"""
    __tablename__ = "ml_model_performance"
    __table_args__ = (
        Index("idx_mlperf_ticker_date", "ticker", "eval_date"),
    )

    id:                Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker:            Mapped[str]             = mapped_column(String(20), nullable=False)
    eval_date:         Mapped[date]            = mapped_column(Date, nullable=False)
    accuracy_7d:       Mapped[Optional[float]] = mapped_column(Float)
    accuracy_30d:      Mapped[Optional[float]] = mapped_column(Float)
    sample_count:      Mapped[int]             = mapped_column(Integer, default=0)
    retrain_triggered: Mapped[bool]            = mapped_column(Boolean, default=False)
    created_at:        Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now())
