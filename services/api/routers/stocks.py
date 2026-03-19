"""GET /api/v1/stocks 라우터 - 분봉 데이터 제공"""

import asyncio
import os
import time
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/stocks", tags=["Stocks"])

KIS_APP_KEY    = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_REST_BASE  = "https://openapi.koreainvestment.com:9443"

# 액세스 토큰 인메모리 캐시
_kis_token_cache: dict = {"token": "", "expires_at": 0.0}


class CandlePoint(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def _get_kis_token() -> str:
    import requests
    now = time.time()
    if _kis_token_cache["token"] and now < _kis_token_cache["expires_at"] - 600:
        return _kis_token_cache["token"]
    resp = requests.post(
        f"{KIS_REST_BASE}/oauth2/tokenP",
        json={"grant_type": "client_credentials", "appkey": KIS_APP_KEY, "appsecret": KIS_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    _kis_token_cache["token"] = data["access_token"]
    _kis_token_cache["expires_at"] = now + int(data.get("expires_in", 86400))
    return _kis_token_cache["token"]


def _fetch_kr_minute_candles(ticker: str) -> list[dict]:
    """KIS REST API로 오늘 1분봉 데이터 조회 (장중 전체)"""
    import requests

    if not KIS_APP_KEY or not KIS_APP_SECRET:
        return []
    try:
        token = _get_kis_token()
    except Exception:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "appkey":    KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id":     "FHKST03010200",
        "custtype":  "P",
    }

    # KST 기준 현재 시각
    now_kst = datetime.utcnow() + timedelta(hours=9)
    if now_kst.hour < 9:
        # 장 전 — 전일 종가 기준
        now_kst -= timedelta(days=1)
        query_time = "153000"
    elif now_kst.hour > 15 or (now_kst.hour == 15 and now_kst.minute >= 30):
        query_time = "153000"
    else:
        query_time = now_kst.strftime("%H%M%S")

    today_str        = now_kst.strftime("%Y%m%d")
    market_open_str  = today_str + "090000"

    all_candles: list[dict] = []

    for _ in range(14):  # 14회 × 30봉 = 420분 > 전체 거래일(390분)
        params = {
            "FID_ETC_CLS_CODE":       "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         ticker,
            "FID_INPUT_HOUR_1":       query_time,
            "FID_PW_DATA_INCU_YN":    "Y",
        }
        try:
            result = requests.get(
                f"{KIS_REST_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                headers=headers,
                params=params,
                timeout=10,
            ).json()
        except Exception:
            break

        items = result.get("output2", [])
        if not items:
            break

        done = False
        for item in items:
            d = item.get("stck_bsop_date", "")
            t = item.get("stck_cntg_hour", "")
            if not d or not t:
                continue
            if d + t < market_open_str:
                done = True
                break
            try:
                dt = datetime.strptime(f"{d}{t}", "%Y%m%d%H%M%S")
                all_candles.append({
                    "timestamp": dt.isoformat(),
                    "open":   round(float(item.get("stck_oprc", 0)), 2),
                    "high":   round(float(item.get("stck_hgpr", 0)), 2),
                    "low":    round(float(item.get("stck_lwpr", 0)), 2),
                    "close":  round(float(item.get("stck_prpr", 0)), 2),
                    "volume": int(item.get("cntg_vol", 0)),
                })
            except Exception:
                continue

        if done:
            break

        # 다음 페이지: 이번 배치에서 가장 오래된 시각 - 1분
        oldest = items[-1]
        old_d, old_t = oldest.get("stck_bsop_date", ""), oldest.get("stck_cntg_hour", "")
        if not old_d or not old_t or old_d + old_t <= market_open_str:
            break
        old_dt = datetime.strptime(f"{old_d}{old_t}", "%Y%m%d%H%M%S") - timedelta(minutes=1)
        query_time = old_dt.strftime("%H%M%S")

    all_candles.sort(key=lambda x: x["timestamp"])
    return all_candles


def _fetch_kr_daily_candles(ticker: str, days: int) -> list[dict]:
    """pykrx 일봉 데이터 (3D / 5D용)"""
    try:
        from pykrx import stock as krx
        end   = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2 + 10)).strftime("%Y%m%d")
        df = krx.get_market_ohlcv_by_date(start, end, ticker)
        if df.empty:
            return []
        df = df.iloc[:, :5]
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        df = df.tail(days)
        return [
            {
                "timestamp": str(idx.date()) + "T09:00:00",
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for idx, row in df.iterrows()
        ]
    except Exception:
        return []


def _fetch_us_candles(ticker: str, days: int) -> list[dict]:
    import yfinance as yf

    stock = yf.Ticker(ticker)
    df = stock.history(period=f"{days}d", interval="1m")
    if df.empty:
        return []
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return [
        {
            "timestamp": idx.isoformat(),
            "open":   round(float(row["Open"]),  4),
            "high":   round(float(row["High"]),  4),
            "low":    round(float(row["Low"]),   4),
            "close":  round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        }
        for idx, row in df.iterrows()
    ]


@router.get("/{ticker}/candles", response_model=list[CandlePoint])
async def get_candles(
    ticker: str,
    days: int = Query(1, ge=1, le=5),
):
    clean = ticker.upper().replace("KR:", "")
    is_kr = ticker.upper().startswith("KR:") or clean.isdigit()
    loop  = asyncio.get_running_loop()

    try:
        if is_kr:
            if days == 1:
                # 1일: KIS REST API 분봉
                data = await loop.run_in_executor(None, _fetch_kr_minute_candles, clean)
            else:
                # 3D/5D: pykrx 일봉
                data = await loop.run_in_executor(None, _fetch_kr_daily_candles, clean, days)
        else:
            data = await loop.run_in_executor(None, _fetch_us_candles, clean, days)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
