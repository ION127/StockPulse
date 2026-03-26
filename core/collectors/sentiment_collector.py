"""
감성 / 관심도 데이터 수집
- Google Trends: 종목 검색 관심도
- 네이버 금융 뉴스 감성: 제목 기반 간단 스코어링
"""

import logging
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 긍정/부정 키워드 (한국어 뉴스 제목 기반 감성 분석)
_POSITIVE_KW = ["급등", "신고가", "호실적", "매수", "상향", "기대", "흑자", "수주", "성장", "돌파", "반등"]
_NEGATIVE_KW = ["급락", "신저가", "부진", "매도", "하향", "우려", "적자", "손실", "하락", "이탈", "경고"]


def get_google_trends(keywords: list[str], days_back: int = 60) -> pd.DataFrame:
    """
    Google Trends 검색량 지수 (0-100 정규화, 주간 → 일별 보간)

    Args:
        keywords: 검색어 목록 (최대 5개)
        days_back: 최근 N일 (최대 270일)

    Returns:
        DataFrame, index=date, columns=keywords
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="ko", tz=540, timeout=(10, 25), retries=2, backoff_factor=0.5)
        kw_list = [str(k) for k in keywords[:5]]

        days = min(days_back, 270)
        timeframe = f"today {days}-d" if days <= 90 else f"today {days // 30}-m"

        pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo="KR")
        time.sleep(1.5)  # Rate limit 방지

        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame()

        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index.name = "date"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])

        # 주간 데이터를 일별로 리샘플링 (linear 보간)
        df = df.resample("D").interpolate(method="linear")
        return df

    except Exception as e:
        logger.warning(f"[Trends] Google Trends 수집 실패: {e}")
        return pd.DataFrame()


def get_naver_news_sentiment(ticker: str, max_articles: int = 20) -> Optional[float]:
    """
    네이버 금융 뉴스 제목 기반 감성 점수
    -1.0 (매우 부정) ~ +1.0 (매우 긍정)
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        clean = ticker.replace("KR:", "").replace(".KS", "").replace(".KQ", "")
        url = f"https://finance.naver.com/item/news_news.naver?code={clean}&page=1"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.content, "html.parser")
        titles = [a.get_text(strip=True) for a in soup.select("td.title a")][:max_articles]

        if not titles:
            return None

        scores = []
        for title in titles:
            pos = sum(1 for kw in _POSITIVE_KW if kw in title)
            neg = sum(1 for kw in _NEGATIVE_KW if kw in title)
            if pos + neg > 0:
                scores.append((pos - neg) / (pos + neg))
            else:
                scores.append(0.0)

        return round(sum(scores) / len(scores), 4)

    except Exception as e:
        logger.debug(f"[Sentiment] 네이버 감성 수집 실패 ({ticker}): {e}")
        return None


def get_discussion_activity(ticker: str) -> dict:
    """
    네이버 종목토론실 최근 게시물 수 (활성도 지표)

    Returns: dict(post_count_today, avg_likes)
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        clean = ticker.replace("KR:", "").replace(".KS", "").replace(".KQ", "")
        url = f"https://finance.naver.com/item/board.naver?code={clean}"
        headers = {"User-Agent": "Mozilla/5.0"}

        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.content, "html.parser")
        rows = soup.select("table.type2 tr")

        count = 0
        total_likes = 0
        for row in rows[:20]:
            cells = row.find_all("td")
            if len(cells) >= 4:
                count += 1
                try:
                    likes = int(cells[-2].get_text(strip=True))
                    total_likes += likes
                except Exception:
                    pass

        return {
            "discussion_count": count,
            "avg_likes": round(total_likes / count, 2) if count > 0 else 0,
        }

    except Exception as e:
        logger.debug(f"[Sentiment] 토론실 활성도 수집 실패 ({ticker}): {e}")
        return {}
