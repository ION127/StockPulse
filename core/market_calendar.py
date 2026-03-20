"""
마켓 캘린더 유틸리티 — 미국(NYSE) / 한국(KRX) 장 운영 시간 관리

공개 함수:
  is_us_market_open()       → NYSE 현재 개장 여부 (bool)
  is_kr_market_open()       → KRX 현재 개장 여부 (bool)
  seconds_until_us_open()   → NYSE 다음 개장까지 남은 초 (float)
  seconds_until_kr_open()   → KRX 다음 개장까지 남은 초 (float)

공휴일 목록은 매년 갱신 필요 (NYSE_HOLIDAYS, KRX_HOLIDAYS).
현재: 2025-2026년 기준
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET  = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

# ── NYSE 공휴일 (2025–2026) ────────────────────────────────────────────────────
NYSE_HOLIDAYS: set[date] = {
    # 2025
    date(2025,  1,  1),   # New Year's Day
    date(2025,  1, 20),   # Martin Luther King Jr. Day
    date(2025,  2, 17),   # Presidents' Day
    date(2025,  4, 18),   # Good Friday
    date(2025,  5, 26),   # Memorial Day
    date(2025,  6, 19),   # Juneteenth
    date(2025,  7,  4),   # Independence Day
    date(2025,  9,  1),   # Labor Day
    date(2025, 11, 27),   # Thanksgiving Day
    date(2025, 12, 25),   # Christmas Day
    # 2026
    date(2026,  1,  1),   # New Year's Day
    date(2026,  1, 19),   # Martin Luther King Jr. Day
    date(2026,  2, 16),   # Presidents' Day
    date(2026,  4,  3),   # Good Friday
    date(2026,  5, 25),   # Memorial Day
    date(2026,  6, 19),   # Juneteenth
    date(2026,  7,  3),   # Independence Day (observed)
    date(2026,  9,  7),   # Labor Day
    date(2026, 11, 26),   # Thanksgiving Day
    date(2026, 12, 25),   # Christmas Day
}

# ── KRX 공휴일 (2025–2026) ────────────────────────────────────────────────────
KRX_HOLIDAYS: set[date] = {
    # 2025
    date(2025,  1,  1),   # 신정
    date(2025,  1, 28),   # 설날 연휴
    date(2025,  1, 29),   # 설날
    date(2025,  1, 30),   # 설날 연휴
    date(2025,  3,  1),   # 삼일절
    date(2025,  5,  1),   # 근로자의 날
    date(2025,  5,  5),   # 어린이날
    date(2025,  5,  6),   # 대체공휴일 (부처님오신날 — 어린이날과 겹침)
    date(2025,  6,  6),   # 현충일
    date(2025,  8, 15),   # 광복절
    date(2025, 10,  3),   # 개천절
    date(2025, 10,  6),   # 추석 연휴
    date(2025, 10,  7),   # 추석
    date(2025, 10,  8),   # 추석 연휴
    date(2025, 10,  9),   # 한글날
    date(2025, 12, 25),   # 크리스마스
    date(2025, 12, 31),   # 연말 휴장
    # 2026
    date(2026,  1,  1),   # 신정
    date(2026,  2, 16),   # 설날 연휴
    date(2026,  2, 17),   # 설날
    date(2026,  2, 18),   # 설날 연휴
    date(2026,  3,  1),   # 삼일절 (일요일)
    date(2026,  3,  2),   # 삼일절 대체공휴일
    date(2026,  5,  1),   # 근로자의 날
    date(2026,  5,  5),   # 어린이날
    date(2026,  5, 25),   # 부처님오신날
    date(2026,  6,  6),   # 현충일 (토요일 — KRX 자체 판단)
    date(2026,  8, 17),   # 광복절 대체 (일요일)
    date(2026,  9, 24),   # 추석 연휴
    date(2026,  9, 25),   # 추석
    date(2026,  9, 26),   # 추석 연휴
    date(2026, 10,  9),   # 한글날
    date(2026, 12, 25),   # 크리스마스
    date(2026, 12, 31),   # 연말 휴장
}

# ── 장 운영 시간 ──────────────────────────────────────────────────────────────
_US_OPEN  = time(9, 30)
_US_CLOSE = time(16,  0)
_KR_OPEN  = time(9,  0)
_KR_CLOSE = time(15, 30)


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _is_trading_day(d: date, holidays: set[date]) -> bool:
    """주말 + 공휴일 제외 거래일 여부."""
    return d.weekday() < 5 and d not in holidays


def _seconds_until_open(
    now_local: datetime,
    open_time: time,
    holidays: set[date],
) -> float:
    """
    현지 시간 기준으로 다음 개장 시각까지 남은 초 반환.
    이미 개장 중이면 0 반환.
    """
    today = now_local.date()

    # 오늘이 거래일이고 아직 개장 전
    if _is_trading_day(today, holidays) and now_local.time() < open_time:
        next_open = datetime.combine(today, open_time, tzinfo=now_local.tzinfo)
        return (next_open - now_local).total_seconds()

    # 다음 거래일 탐색 (최대 10일)
    candidate = today + timedelta(days=1)
    for _ in range(10):
        if _is_trading_day(candidate, holidays):
            next_open = datetime.combine(candidate, open_time, tzinfo=now_local.tzinfo)
            return max(0.0, (next_open - now_local).total_seconds())
        candidate += timedelta(days=1)

    # 비상 fallback
    return 86_400.0


# ── 공개 API ──────────────────────────────────────────────────────────────────

def is_us_market_open(now: datetime | None = None) -> bool:
    """NYSE가 현재 개장 중인지 반환 (ET 기준)."""
    now_et = (now or datetime.now(ET)).astimezone(ET)
    if not _is_trading_day(now_et.date(), NYSE_HOLIDAYS):
        return False
    return _US_OPEN <= now_et.time() < _US_CLOSE


def is_kr_market_open(now: datetime | None = None) -> bool:
    """KRX가 현재 개장 중인지 반환 (KST 기준)."""
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    if not _is_trading_day(now_kst.date(), KRX_HOLIDAYS):
        return False
    return _KR_OPEN <= now_kst.time() < _KR_CLOSE


def seconds_until_us_open(now: datetime | None = None) -> float:
    """NYSE 다음 개장까지 남은 초 반환. 이미 개장 중이면 0."""
    now_et = (now or datetime.now(ET)).astimezone(ET)
    if is_us_market_open(now_et):
        return 0.0
    return _seconds_until_open(now_et, _US_OPEN, NYSE_HOLIDAYS)


def seconds_until_kr_open(now: datetime | None = None) -> float:
    """KRX 다음 개장까지 남은 초 반환. 이미 개장 중이면 0."""
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    if is_kr_market_open(now_kst):
        return 0.0
    return _seconds_until_open(now_kst, _KR_OPEN, KRX_HOLIDAYS)
