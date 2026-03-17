"""
뉴스 수집 모듈
- NewsAPI: 영문 뉴스
- 네이버 뉴스 RSS: 한국어 뉴스
- Google News RSS: 보조
"""

import os
import requests
import feedparser
import logging
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


def fetch_english_news(
    keywords: list[str],
    max_articles: int = 5,
    days_back: int = 3,
) -> list[dict]:
    """
    NewsAPI로 영문 뉴스 수집
    무료 플랜: 월 100 requests
    """
    articles = []

    # NewsAPI 사용 가능한 경우
    if NEWS_API_KEY:
        query = " OR ".join(keywords[:3])  # 최대 3개 키워드
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "language": "en",
                "pageSize": max_articles,
                "apiKey": NEWS_API_KEY,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for article in data.get("articles", []):
                    articles.append({
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("url", ""),
                        "published_at": article.get("publishedAt", ""),
                        "source": article.get("source", {}).get("name", ""),
                        "language": "en",
                    })
        except Exception as e:
            logger.warning(f"NewsAPI 오류: {e}")

    # Google News RSS (API 없어도 동작)
    if len(articles) < max_articles:
        query = "+".join(keywords[:3])
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[: max_articles - len(articles)]:
                articles.append({
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                    "source": "Google News",
                    "language": "en",
                })
        except Exception as e:
            logger.warning(f"Google News RSS 오류: {e}")

    return articles[:max_articles]


def fetch_korean_news(
    keywords: list[str],
    max_articles: int = 5,
) -> list[dict]:
    """
    네이버 뉴스 RSS로 한국어 뉴스 수집
    """
    articles = []

    for keyword in keywords[:2]:  # 키워드 2개까지
        try:
            # 네이버 뉴스 검색 RSS
            encoded_kw = requests.utils.quote(keyword)
            rss_url = f"https://news.naver.com/main/search/search.naver?query={encoded_kw}&sort=1"

            # 네이버 뉴스 RSS (공개 API)
            naver_rss = f"https://news.naver.com/main/rss/searchNews.naver?query={encoded_kw}"
            feed = feedparser.parse(naver_rss)

            for entry in feed.entries[:max_articles]:
                articles.append({
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                    "source": "Naver News",
                    "language": "kr",
                })
        except Exception as e:
            logger.warning(f"네이버 뉴스 RSS 오류 ({keyword}): {e}")

    # Google News 한국어 버전 보조
    if len(articles) < max_articles:
        query = "+".join(keywords[:2])
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[: max_articles - len(articles)]:
                articles.append({
                    "title": entry.get("title", ""),
                    "description": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                    "source": "Google News KR",
                    "language": "kr",
                })
        except Exception as e:
            logger.warning(f"Google News KR RSS 오류: {e}")

    return articles[:max_articles]


def fetch_news_for_anomaly(
    ticker: str,
    category_name: str,
    keywords_en: list[str],
    keywords_kr: list[str],
    max_per_lang: int = 4,
) -> dict[str, list[dict]]:
    """
    이상값 발생 종목에 대한 영문/한국어 뉴스 동시 수집
    """
    # 티커 자체도 키워드에 추가
    ticker_clean = ticker.replace("KR:", "")
    search_keywords_en = [ticker_clean] + keywords_en
    search_keywords_kr = keywords_kr

    en_news = fetch_english_news(search_keywords_en, max_articles=max_per_lang)
    kr_news = fetch_korean_news(search_keywords_kr, max_articles=max_per_lang)

    logger.info(
        f"{ticker} ({category_name}): 영문 뉴스 {len(en_news)}건, 한국어 뉴스 {len(kr_news)}건 수집"
    )
    return {"en": en_news, "kr": kr_news}


def format_news_for_prompt(news_data: dict[str, list[dict]]) -> str:
    """뉴스를 Claude 프롬프트용 텍스트로 변환"""
    lines = []

    if news_data.get("en"):
        lines.append("=== English News ===")
        for i, article in enumerate(news_data["en"], 1):
            lines.append(f"{i}. [{article['source']}] {article['title']}")
            if article.get("description"):
                desc = article["description"][:200]
                lines.append(f"   {desc}")
            lines.append("")

    if news_data.get("kr"):
        lines.append("=== 한국어 뉴스 ===")
        for i, article in enumerate(news_data["kr"], 1):
            lines.append(f"{i}. [{article['source']}] {article['title']}")
            if article.get("description"):
                # HTML 태그 제거
                desc = BeautifulSoup(article["description"], "html.parser").get_text()[:200]
                lines.append(f"   {desc}")
            lines.append("")

    return "\n".join(lines)
