"""유저 데이터 라우터 (Phase 6)

GET    /api/v1/users/watchlist              — 관심 종목 목록
POST   /api/v1/users/watchlist              — 관심 종목 추가
DELETE /api/v1/users/watchlist/{ticker}     — 관심 종목 삭제

GET    /api/v1/users/portfolio              — 포트폴리오 목록
POST   /api/v1/users/portfolio              — 종목 추가 (이미 있으면 덮어쓰기)
DELETE /api/v1/users/portfolio/{ticker}     — 종목 삭제

GET    /api/v1/users/alerts                 — 알림 설정 목록
POST   /api/v1/users/alerts                 — 알림 설정 추가/수정
DELETE /api/v1/users/alerts/{ticker}        — 알림 설정 삭제
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_db
from db.models import AlertSetting, Portfolio, User, Watchlist
from schemas.user import (
    AlertSettingItem,
    AlertSettingUpsertRequest,
    PortfolioItem,
    PortfolioUpsertRequest,
    WatchlistAddRequest,
    WatchlistItem,
)
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/users", tags=["User"])


# ── 관심 종목 ──────────────────────────────────────────────────────────────

@router.get("/watchlist", response_model=list[WatchlistItem])
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.added_at.desc())
    )
    return result.scalars().all()


@router.post("/watchlist", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
async def add_watchlist(
    body: WatchlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticker = body.ticker.upper()
    existing = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.ticker == ticker)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 관심 종목에 추가된 티커입니다")

    item = Watchlist(user_id=current_user.id, ticker=ticker)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(Watchlist).where(
            Watchlist.user_id == current_user.id,
            Watchlist.ticker == ticker.upper(),
        )
    )
    await db.commit()


# ── 포트폴리오 ─────────────────────────────────────────────────────────────

@router.get("/portfolio", response_model=list[PortfolioItem])
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.added_at.desc())
    )
    return result.scalars().all()


@router.post("/portfolio", response_model=PortfolioItem, status_code=status.HTTP_201_CREATED)
async def upsert_portfolio(
    body: PortfolioUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """종목 추가. 이미 있으면 수량/평균단가 업데이트."""
    ticker = body.ticker.upper()
    result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == current_user.id, Portfolio.ticker == ticker)
    )
    item = result.scalar_one_or_none()

    if item:
        item.quantity  = body.quantity
        item.avg_price = body.avg_price
    else:
        item = Portfolio(
            user_id=current_user.id,
            ticker=ticker,
            quantity=body.quantity,
            avg_price=body.avg_price,
        )
        db.add(item)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/portfolio/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_portfolio(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.ticker == ticker.upper(),
        )
    )
    await db.commit()


# ── 알림 설정 ──────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=list[AlertSettingItem])
async def get_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertSetting).where(AlertSetting.user_id == current_user.id)
    )
    return result.scalars().all()


@router.post("/alerts", response_model=AlertSettingItem, status_code=status.HTTP_201_CREATED)
async def upsert_alert(
    body: AlertSettingUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticker = body.ticker.upper()
    result = await db.execute(
        select(AlertSetting).where(AlertSetting.user_id == current_user.id, AlertSetting.ticker == ticker)
    )
    item = result.scalar_one_or_none()

    if item:
        item.threshold_pct = body.threshold_pct
        item.alert_channel = body.alert_channel
        item.quiet_start   = body.quiet_start
        item.quiet_end     = body.quiet_end
    else:
        item = AlertSetting(
            user_id=current_user.id,
            ticker=ticker,
            threshold_pct=body.threshold_pct,
            alert_channel=body.alert_channel,
            quiet_start=body.quiet_start,
            quiet_end=body.quiet_end,
        )
        db.add(item)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/alerts/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_alert(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(AlertSetting).where(
            AlertSetting.user_id == current_user.id,
            AlertSetting.ticker == ticker.upper(),
        )
    )
    await db.commit()
