"""
주식 데이터 수집 모듈
- yfinance: 미국/글로벌 주식
- pykrx: 한국 주식
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def fetch_us_stocks(tickers: list[str], period_days: int = 30) -> dict[str, pd.DataFrame]:
    """
    미국 주식 데이터 수집 (yfinance)
    반환: {ticker: DataFrame(Date, Open, High, Low, Close, Volume)}
    """
    results = {}
    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_days)

    logger.info(f"미국 주식 {len(tickers)}개 수집 중...")

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date, end=end_date)
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                results[ticker] = df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            logger.warning(f"{ticker} 수집 실패: {e}")

    logger.info(f"미국 주식 {len(results)}개 수집 완료")
    return results


def fetch_kr_stocks(tickers: list[str], period_days: int = 30) -> dict[str, pd.DataFrame]:
    """
    한국 주식 데이터 수집 (pykrx)
    반환: {ticker: DataFrame(Date, Open, High, Low, Close, Volume)}
    """
    try:
        from pykrx import stock as krx_stock
    except ImportError:
        logger.error("pykrx가 설치되지 않았습니다: pip install pykrx")
        return {}

    results = {}
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=period_days)).strftime("%Y%m%d")

    logger.info(f"한국 주식 {len(tickers)}개 수집 중...")

    for ticker in tickers:
        try:
            df = krx_stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
            if not df.empty:
                # pykrx 버전에 따라 6~7컬럼 반환 → 앞 5개(OHLCV)만 사용
                df = df.iloc[:, :5]
                df.columns = ["Open", "High", "Low", "Close", "Volume"]
                results[f"KR:{ticker}"] = df
        except Exception as e:
            logger.warning(f"KR:{ticker} 수집 실패: {e}")

    logger.info(f"한국 주식 {len(results)}개 수집 완료")
    return results


def detect_anomalies(
    stock_data: dict[str, pd.DataFrame],
    percent_threshold: float = 5.0,
    zscore_threshold: float = 2.5,
    lookback_days: int = 20,
) -> list[dict]:
    """
    이상값 탐지 (급등/급락)
    두 가지 방법 병행:
    1. 단순 퍼센트 변화율 (당일 기준)
    2. Z-score (최근 N일 기준 통계적 이상값)
    """
    anomalies = []
    today = datetime.now().date()

    for ticker, df in stock_data.items():
        if df.empty or len(df) < 2:
            continue

        # 일별 수익률 계산
        df = df.copy()
        df["return_pct"] = df["Close"].pct_change() * 100

        # 최근 데이터만 분석
        recent_df = df.tail(lookback_days)
        if len(recent_df) < 5:
            continue

        # Z-score 계산
        mean_return = recent_df["return_pct"].mean()
        std_return = recent_df["return_pct"].std()

        for date, row in recent_df.iterrows():
            ret = row["return_pct"]
            if pd.isna(ret):
                continue

            # Z-score
            zscore = (ret - mean_return) / std_return if std_return > 0 else 0

            # 이상값 판단: 퍼센트 OR Z-score 기준 충족
            is_anomaly_pct = abs(ret) >= percent_threshold
            is_anomaly_zscore = abs(zscore) >= zscore_threshold

            if is_anomaly_pct or is_anomaly_zscore:
                anomaly_date = date.date() if hasattr(date, "date") else date
                anomalies.append({
                    "ticker": ticker,
                    "date": anomaly_date,
                    "return_pct": round(ret, 2),
                    "zscore": round(zscore, 2),
                    "close_price": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                    "direction": "급등" if ret > 0 else "급락",
                    "is_recent": (today - anomaly_date).days <= 5,  # 5일 이내 (주말 포함 고려)
                })

    # 최신순 정렬
    anomalies.sort(key=lambda x: (x["date"], abs(x["return_pct"])), reverse=True)
    return anomalies


def classify_event_type(
    anomalies: list[dict],
    categories: dict,
    sector_trigger_count: int = 2,
    market_trigger_sectors: int = 3,
) -> list[dict]:
    """
    이상값 이벤트 유형 분류:
      - INDIVIDUAL : 해당 종목만 이상값 (개별 이벤트)
      - SECTOR     : 같은 섹터 내 N개 이상 종목이 같은 방향으로 이상값 (섹터 이벤트)
      - MARKET     : N개 이상 섹터가 같은 방향으로 이상값 (시장 전체 이벤트)

    sector_trigger_count  : 섹터 이벤트로 보려면 같은 섹터에서 몇 개 이상 터져야 하는지
    market_trigger_sectors: 시장 전체 이벤트로 보려면 몇 개 이상 섹터가 함께 움직여야 하는지
    """
    # ticker -> category 역매핑
    ticker_to_category = {}
    for cat_name, cat_data in categories.items():
        for t in cat_data.get("tickers_us", []):
            ticker_to_category[t] = cat_name
        for t in cat_data.get("tickers_kr", []):
            ticker_to_category[f"KR:{t}"] = cat_name

    # 날짜별로 이상값 묶기 (같은 날 발생한 것끼리 비교)
    from collections import defaultdict
    by_date = defaultdict(list)
    for a in anomalies:
        by_date[a["date"]].append(a)

    result = []
    for a in anomalies:
        same_day = by_date[a["date"]]
        my_sector = ticker_to_category.get(a["ticker"], "기타")
        my_dir = a["direction"]  # 급등 or 급락

        # 같은 날, 같은 섹터, 같은 방향으로 움직인 종목 수
        sector_peers = [
            x for x in same_day
            if ticker_to_category.get(x["ticker"], "기타") == my_sector
            and x["direction"] == my_dir
            and x["ticker"] != a["ticker"]
        ]

        # 같은 날, 같은 방향으로 움직인 섹터 수
        moving_sectors = set(
            ticker_to_category.get(x["ticker"], "기타")
            for x in same_day
            if x["direction"] == my_dir
        )

        if len(moving_sectors) >= market_trigger_sectors:
            event_type = "MARKET"      # 시장 전체 이벤트
        elif len(sector_peers) >= sector_trigger_count - 1:
            event_type = "SECTOR"      # 섹터 이벤트
        else:
            event_type = "INDIVIDUAL"  # 개별 이벤트

        result.append({
            **a,
            "event_type": event_type,
            "sector": my_sector,
            "sector_peer_count": len(sector_peers) + 1,   # 자신 포함
            "moving_sector_count": len(moving_sectors),
        })

    return result


def get_sector_anomaly_summary(
    anomalies: list[dict],
    categories: dict,
) -> dict[str, list[dict]]:
    """
    이상값을 섹터별로 그룹화
    반환: {카테고리명: [이상값 목록]}
    """
    sector_map = {}

    # 역방향 매핑: ticker -> category
    ticker_to_category = {}
    for cat_name, cat_data in categories.items():
        for ticker in cat_data.get("tickers_us", []):
            ticker_to_category[ticker] = cat_name
        for ticker in cat_data.get("tickers_kr", []):
            ticker_to_category[f"KR:{ticker}"] = cat_name

    for anomaly in anomalies:
        ticker = anomaly["ticker"]
        category = ticker_to_category.get(ticker, "기타 (Others)")
        if category not in sector_map:
            sector_map[category] = []
        sector_map[category].append(anomaly)

    return sector_map
