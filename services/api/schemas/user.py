"""사용자 인증 & 포트폴리오 관련 Pydantic 스키마 (Phase 6)"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ── 인증 ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str
    tier: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 관심 종목 ─────────────────────────────────────────────────────────────

class WatchlistItem(BaseModel):
    id: int
    ticker: str
    added_at: datetime

    model_config = {"from_attributes": True}


class WatchlistAddRequest(BaseModel):
    ticker: str


# ── 포트폴리오 ────────────────────────────────────────────────────────────

class PortfolioItem(BaseModel):
    id: int
    ticker: str
    quantity: float
    avg_price: float
    added_at: datetime

    model_config = {"from_attributes": True}


class PortfolioUpsertRequest(BaseModel):
    ticker: str
    quantity: float
    avg_price: float


# ── 알림 설정 ─────────────────────────────────────────────────────────────

class AlertSettingItem(BaseModel):
    id: int
    ticker: str
    threshold_pct: float
    alert_channel: str
    quiet_start: Optional[int]
    quiet_end: Optional[int]

    model_config = {"from_attributes": True}


class AlertSettingUpsertRequest(BaseModel):
    ticker: str
    threshold_pct: float = 3.0
    alert_channel: str = "email"   # email / kakao / browser
    quiet_start: Optional[int] = None
    quiet_end: Optional[int] = None
