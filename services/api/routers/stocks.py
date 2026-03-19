"""GET /api/v1/stocks 라우터 - 분봉 데이터 제공"""

import asyncio
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/stocks", tags=["Stocks"])


class CandlePoint(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


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


def _fetch_kr_candles(ticker: str, days: int) -> list[dict]:
    """한국 주식 — 일봉 데이터 (1분봉 미지원)"""
    from datetime import datetime, timedelta
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


@router.get("/{ticker}/candles", response_model=list[CandlePoint])
async def get_candles(
    ticker: str,
    days: int = Query(1, ge=1, le=5),
):
    clean   = ticker.upper().replace("KR:", "")
    is_kr   = ticker.upper().startswith("KR:") or clean.isdigit()
    loop    = asyncio.get_running_loop()

    try:
        if is_kr:
            data = await loop.run_in_executor(None, _fetch_kr_candles, clean, days)
        else:
            data = await loop.run_in_executor(None, _fetch_us_candles, clean, days)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
