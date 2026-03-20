"""JWT 인증 서비스 (Phase 6)

- 비밀번호 해싱: passlib[bcrypt]
- 토큰 발급: python-jose[cryptography]
- Access Token : 15분
- Refresh Token: 30일
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_db
from db.models import User

# ── 설정 ─────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET 환경변수가 설정되지 않았습니다. k8s secret 또는 .env를 확인하세요.")
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = 15
REFRESH_TOKEN_EXPIRE_DAYS    = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


# ── 비밀번호 ──────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── 토큰 발급 ─────────────────────────────────────────────────────────────

def _create_token(data: dict, expire_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expire_delta
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, tier: str) -> str:
    return _create_token(
        {"sub": str(user_id), "tier": tier, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


# ── 토큰 검증 ─────────────────────────────────────────────────────────────

def _decode_token(token: str, expected_type: str) -> dict:
    """토큰 디코딩. 실패 시 HTTPException 401 발생."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰 타입 불일치")

    return payload


# ── FastAPI 의존성 ─────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authorization: Bearer <access_token> 헤더에서 현재 유저 반환."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다")

    payload = _decode_token(credentials.credentials, "access")
    user_id = int(payload["sub"])

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유저를 찾을 수 없습니다")

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """토큰 없어도 None 반환 (비회원 접근 허용 엔드포인트용)."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


def decode_refresh_token(token: str) -> int:
    """Refresh Token → user_id 반환."""
    payload = _decode_token(token, "refresh")
    return int(payload["sub"])
