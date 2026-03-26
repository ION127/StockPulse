"""
매크로 경제 지표 수집
- yfinance: VIX, 환율, 유가, KOSPI, NASDAQ, 금, 미국채금리
- 한국은행 ECOS API: 기준금리 (선택)
- CNN Fear & Greed Index
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

BOK_API_KEY = os.getenv("BOK_API_KEY", "")


def get_market_indices(days_back: int = 90) -> pd.DataFrame:
    """
    주요 글로벌 지수 및 매크로 지표 (일별)

    Returns columns: vix, usd_krw, oil_price, kospi, nasdaq,
                     gold_price, us_10y_yield, us_2y_yield, dxy
    """
    try:
        import yfinance as yf

        end = datetime.now()
        start = end - timedelta(days=days_back + 10)  # 여유분

        symbols = {
            "^VIX":   "vix",           # CBOE 공포지수
            "KRW=X":  "usd_krw",       # 달러/원 환율
            "CL=F":   "oil_price",     # WTI 유가
            "^KS11":  "kospi",         # KOSPI 지수
            "^IXIC":  "nasdaq",        # NASDAQ
            "GC=F":   "gold_price",    # 금 선물
            "^TNX":   "us_10y_yield",  # 미국 10년 국채금리
            "^IRX":   "us_3m_yield",   # 미국 3개월 국채금리 (단기)
            "DX-Y.NYB": "dxy",         # 달러 인덱스
            "^KQ11":  "kosdaq",        # KOSDAQ
        }

        frames: dict[str, pd.Series] = {}
        for symbol, name in symbols.items():
            try:
                data = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
                if not data.empty:
                    close = data["Close"]
                    if hasattr(close, "squeeze"):
                        close = close.squeeze()
                    frames[name] = close
            except Exception as e:
                logger.debug(f"[Macro] {symbol} 수집 실패: {e}")

        if not frames:
            return pd.DataFrame()

        df = pd.DataFrame(frames)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index.name = "date"

        # 파생 지표
        if "us_10y_yield" in df.columns and "us_3m_yield" in df.columns:
            df["yield_curve"] = df["us_10y_yield"] - df["us_3m_yield"]  # 장단기 금리차

        if "vix" in df.columns:
            df["vix_change_5d"] = df["vix"].pct_change(5)

        if "kospi" in df.columns:
            df["kospi_return_5d"] = df["kospi"].pct_change(5)
            df["kospi_return_20d"] = df["kospi"].pct_change(20)

        return df.ffill().tail(days_back)

    except Exception as e:
        logger.warning(f"[Macro] 시장 지수 수집 실패: {e}")
        return pd.DataFrame()


def _bok_fetch_series(
    stat_code: str,
    item_code: str,
    period: str,
    start_date: str,
    end_date: str,
    col_name: str,
) -> pd.DataFrame:
    """
    BOK ECOS API 공통 시계열 수집 헬퍼
    period: "DD"=일별, "MM"=월별, "QQ"=분기별
    """
    if not BOK_API_KEY:
        return pd.DataFrame()
    try:
        import requests
        # 최대 1000건 요청
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{BOK_API_KEY}"
            f"/json/kr/1/1000/{stat_code}/{period}/{start_date}/{end_date}/{item_code}"
        )
        resp = requests.get(url, timeout=15)
        rows = resp.json().get("StatisticSearch", {}).get("row", [])
        if not rows:
            return pd.DataFrame()

        records = []
        for r in rows:
            raw_date = r.get("TIME", "")
            val = r.get("DATA_VALUE", "")
            if not raw_date or val in ("", None):
                continue
            # 날짜 형식 정규화: YYYYMMDD / YYYYMM / YYYYQQ
            if len(raw_date) == 6:  # YYYYMM
                raw_date = raw_date + "01"
            elif len(raw_date) == 5:  # YYYYQ (분기)
                q = int(raw_date[-1])
                raw_date = f"{raw_date[:4]}{(q-1)*3+1:02d}01"
            try:
                records.append((pd.Timestamp(raw_date), float(val)))
            except (ValueError, TypeError):
                continue

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records, columns=["date", col_name]).set_index("date")
        df.index = pd.to_datetime(df.index).normalize()
        df.index.name = "date"
        return df

    except Exception as e:
        logger.debug(f"[BOK] {stat_code}/{item_code} 수집 실패: {e}")
        return pd.DataFrame()


def get_bok_base_rate() -> Optional[float]:
    """한국은행 기준금리 (현재값, BOK_API_KEY 필요)"""
    if not BOK_API_KEY:
        return None
    try:
        import requests
        today = datetime.now().strftime("%Y%m%d")
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{BOK_API_KEY}"
            f"/json/kr/1/1/722Y001/DD/20200101/{today}/0101000"
        )
        resp = requests.get(url, timeout=10)
        rows = resp.json().get("StatisticSearch", {}).get("row", [])
        if rows:
            return float(rows[-1].get("DATA_VALUE", 0))
        return None
    except Exception as e:
        logger.warning(f"[BOK] 기준금리 수집 실패: {e}")
        return None


def get_bok_base_rate_series(days_back: int = 365) -> pd.DataFrame:
    """
    한국은행 기준금리 시계열 (일별 → ffill)

    기준금리 방향(상승/하락 추세)이 주가에 의미있는 신호.
    BOK_API_KEY 없으면 빈 DataFrame 반환.

    Returns columns: bok_base_rate, bok_rate_chg
    """
    end = datetime.now()
    start = end - timedelta(days=days_back + 30)
    df = _bok_fetch_series(
        stat_code="722Y001",
        item_code="0101000",
        period="DD",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        col_name="bok_base_rate",
    )
    if df.empty:
        return pd.DataFrame()

    df["bok_rate_chg"] = df["bok_base_rate"].diff()  # 인상(+)/인하(-)/동결(0)
    return df


def get_bok_investor_deposit(days_back: int = 365) -> pd.DataFrame:
    """
    투자자예탁금 시계열 (시장 유동성 선행지표)

    예탁금 증가 = 주식 매수 대기 자금 유입 → 상승 선행 신호 (1~2주)
    예탁금 감소 = 시장 이탈 신호

    ECOS 통계코드: 901Y056 (위탁자예탁금, 일별)
    BOK_API_KEY 없으면 빈 DataFrame 반환.

    Returns columns: investor_deposit, deposit_chg5, deposit_chg20
    """
    end = datetime.now()
    start = end - timedelta(days=days_back + 30)
    df = _bok_fetch_series(
        stat_code="901Y056",
        item_code="0000000",
        period="DD",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        col_name="investor_deposit",
    )
    if df.empty:
        return pd.DataFrame()

    df["deposit_chg5"]  = df["investor_deposit"].pct_change(5)
    df["deposit_chg20"] = df["investor_deposit"].pct_change(20)
    return df


def get_fear_greed() -> Optional[float]:
    """
    CNN Fear & Greed Index (0=극도 공포, 100=극도 탐욕)
    비공식 엔드포인트 — 실패해도 무시
    """
    try:
        import requests
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        data = resp.json()
        score = data.get("fear_and_greed", {}).get("score")
        return float(score) if score is not None else None
    except Exception:
        return None


def get_us_economic_calendar() -> dict:
    """
    주요 미국 경제 이벤트 여부 (이번 주 FOMC 여부 등)
    단순히 날짜 기반으로 추정
    """
    today = datetime.now()
    # FOMC는 보통 화요일-수요일 (6주에 한 번)
    # 간단히 현재 월 기준으로 추정
    fomc_months = [1, 3, 5, 6, 7, 9, 10, 12]
    result = {
        "is_fomc_month": today.month in fomc_months,
        "day_of_week": today.weekday(),  # 0=월, 4=금
        "is_month_end": today.day >= 25,
        "is_quarter_end": today.month in [3, 6, 9, 12] and today.day >= 25,
    }
    return result
