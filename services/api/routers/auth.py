"""인증 라우터 (Phase 6)

POST /auth/register  — 회원가입
POST /auth/login     — 로그인 → Access + Refresh Token
POST /auth/refresh   — Access Token 재발급
GET  /auth/me        — 현재 로그인 유저 정보
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_db
from db.models import User
from schemas.user import LoginRequest, RegisterRequest, RefreshRequest, TokenResponse, UserResponse
from services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """이메일 + 비밀번호 회원가입"""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        tier="free",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """로그인 — JWT Access Token + Refresh Token 발급"""
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다")

    return TokenResponse(
        access_token=create_access_token(user.id, user.tier),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh Token으로 새 Access Token 발급"""
    user_id = decode_refresh_token(body.refresh_token)

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유저를 찾을 수 없습니다")

    return TokenResponse(
        access_token=create_access_token(user.id, user.tier),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """현재 로그인한 유저 정보"""
    return current_user
