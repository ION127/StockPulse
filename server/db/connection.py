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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://stock:stock1234@localhost:5432/stockdb",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI 의존성 주입용 DB 세션"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """앱 시작 시 테이블 생성 + TimescaleDB Hypertable 설정"""
    from server.db.models import Anomaly, AnalysisResult  # noqa: F401

    async with engine.begin() as conn:
        # 테이블 생성
        await conn.run_sync(Base.metadata.create_all)

        # TimescaleDB Hypertable 설정 (설치된 경우에만)
        try:
            await conn.execute(text(
                "SELECT create_hypertable('anomalies', 'anomaly_date', "
                "if_not_exists => TRUE, migrate_data => TRUE);"
            ))
            logger.info("TimescaleDB hypertable 설정 완료")
        except Exception:
            logger.info("TimescaleDB 미설치 - 일반 PostgreSQL 테이블로 동작")

    logger.info("DB 초기화 완료")
