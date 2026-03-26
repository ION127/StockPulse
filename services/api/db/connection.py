"""
DB 연결 및 테이블 초기화
TimescaleDB(PostgreSQL) - asyncpg + SQLAlchemy 비동기
"""

import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # 로컬 개발 전용 기본값 (K8s에서는 반드시 env var로 주입됨)
    import warnings
    warnings.warn("DATABASE_URL 환경변수가 없습니다. 로컬 개발 기본값을 사용합니다.", stacklevel=2)
    DATABASE_URL = "postgresql+asyncpg://stock:stock1234@localhost:5432/stockdb"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI 의존성 주입용 DB 세션"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db(max_retries: int = 10, retry_interval: float = 3.0):
    """앱 시작 시 테이블 생성 + TimescaleDB Hypertable 설정

    DB가 아직 준비되지 않은 경우 최대 max_retries회 재시도합니다.
    """
    import asyncio
    from db.models import (  # noqa: F401
            Anomaly, AnalysisResult, User, Watchlist, Portfolio, AlertSetting,
            SignalPerformance, StockPrediction, MLModelPerformance,
        )

    for attempt in range(1, max_retries + 1):
        try:
            # 트랜잭션 1: 테이블 생성 (hypertable 설정과 분리하여 롤백 방지)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 트랜잭션 2: hypertable 설정 (실패해도 테이블 생성에 영향 없음)
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(
                        "SELECT create_hypertable('anomalies', 'anomaly_date', "
                        "if_not_exists => TRUE, migrate_data => TRUE);"
                    ))
                    logger.info("TimescaleDB hypertable 설정 완료")
            except Exception as e:
                # 이미 hypertable인 경우 또는 TimescaleDB 미설치 — 정상 진행
                if "already a hypertable" in str(e):
                    logger.info("anomalies 테이블은 이미 hypertable로 설정됨")
                else:
                    logger.info(f"TimescaleDB hypertable 생략 ({e}) - 일반 PostgreSQL 테이블로 동작")

            logger.info("DB 초기화 완료")
            return

        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"DB 초기화 실패 (시도 {attempt}/{max_retries}): {e} "
                    f"— {retry_interval}초 후 재시도"
                )
                await asyncio.sleep(retry_interval)
            else:
                logger.error(f"DB 초기화 최종 실패 ({max_retries}회 시도): {e}")
                raise
