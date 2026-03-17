"""
News Fetcher 서비스 — Phase 3 (Kafka 연동 예정)

현재: stub (Phase 3에서 구현)
Phase 3 역할:
  - Kafka Topic 'anomaly.detected' 구독
  - 영문(NewsAPI + Google RSS) + 한국어(Naver RSS) 뉴스 수집
  - Kafka Topic 'news.fetched'에 발행

환경변수:
  - KAFKA_BOOTSTRAP_SERVERS
  - NEWS_API_KEY
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


def main():
    logger.info("[news-fetcher] Phase 3 미구현 — Kafka 연동 후 활성화")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP}")
    logger.info("  Subscribe: anomaly.detected")
    logger.info("  Publish:   news.fetched")

    # Phase 3 구현 예시:
    # from core.news_fetcher import fetch_news_for_anomaly, format_news_for_prompt
    # from core.stock_categories import STOCK_CATEGORIES
    # from confluent_kafka import Consumer, Producer
    #
    # consumer = Consumer({...})
    # consumer.subscribe(["anomaly.detected"])
    # while True:
    #     msg = consumer.poll(1.0)
    #     anomaly = json.loads(msg.value())
    #     news = fetch_news_for_anomaly(anomaly["ticker"], anomaly["sector"], ...)
    #     producer.produce("news.fetched", value=json.dumps({**anomaly, "news": news}))


if __name__ == "__main__":
    main()
