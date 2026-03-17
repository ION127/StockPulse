"""
News Fetcher 서비스 — Phase 3

역할:
  - Kafka Topic 'anomaly.detected' 구독
  - 영문(NewsAPI + Google RSS) + 한국어(Naver RSS) 뉴스 수집
  - Kafka Topic 'news.fetched'에 발행

메시지 형식 (news.fetched):
  key   : ticker
  value : {
      ...anomaly 필드 전부,
      "news_en"   : [NewsArticle, ...],
      "news_kr"   : [NewsArticle, ...],
      "news_text" : "formatted prompt text"
  }
"""

import json
import logging
import os
import signal
import sys

from confluent_kafka import Consumer, KafkaError, Producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("news-fetcher")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
GROUP_ID = "news-fetcher-group"

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("종료 신호 수신 — 루프 종료 중")
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _delivery_report(err, msg):
    if err:
        logger.error(f"전송 실패 [{msg.topic()}]: {err}")


def main():
    logger.info(f"[news-fetcher] 시작 | Kafka: {KAFKA_BOOTSTRAP}")

    try:
        from core.news_fetcher import fetch_news_for_anomaly, format_news_for_prompt
        from core.stock_categories import STOCK_CATEGORIES
    except ImportError as e:
        logger.error(f"core 모듈 임포트 실패: {e}")
        sys.exit(1)

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
    })
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
    })

    consumer.subscribe(["anomaly.detected"])
    logger.info("구독 시작: anomaly.detected")

    try:
        while _running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Kafka 오류: {msg.error()}")
                continue

            try:
                anomaly = json.loads(msg.value())
                ticker = anomaly["ticker"]
                sector = anomaly.get("sector", "")
                cat_data = STOCK_CATEGORIES.get(sector, {})

                logger.info(f"뉴스 수집 중: {ticker} ({sector})")

                news_data = fetch_news_for_anomaly(
                    ticker,
                    sector,
                    cat_data.get("keywords_en", [ticker.replace("KR:", "")]),
                    cat_data.get("keywords_kr", []),
                )

                en_articles = news_data.get("en", [])
                kr_articles = news_data.get("kr", [])

                payload = {
                    **anomaly,
                    "news_en": en_articles,
                    "news_kr": kr_articles,
                    "news_text": format_news_for_prompt(news_data),
                }

                producer.produce(
                    "news.fetched",
                    key=ticker,
                    value=json.dumps(payload, ensure_ascii=False),
                    callback=_delivery_report,
                )
                producer.flush()

                logger.info(
                    f"news.fetched 발행: {ticker} "
                    f"(영문 {len(en_articles)}건, 한국어 {len(kr_articles)}건)"
                )

            except Exception as e:
                logger.error(f"메시지 처리 오류: {e}", exc_info=True)

    finally:
        consumer.close()
        logger.info("[news-fetcher] 종료")


if __name__ == "__main__":
    main()
