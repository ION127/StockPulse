"""
Stock Collector 서비스 — Phase 3 (Kafka 연동 예정)

현재: stub (Phase 3에서 구현)
Phase 3 역할:
  - yfinance / pykrx로 미국/한국 주가 수집
  - Kafka Topic 'stock.raw.us', 'stock.raw.kr'에 발행
  - K8s CronJob으로 평일 30분마다 실행

Kafka 연동 시 추가 의존성:
  - confluent-kafka 또는 aiokafka
  - KAFKA_BOOTSTRAP_SERVERS 환경변수
"""

import os
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


def main():
    logger.info("[stock-collector] Phase 3 미구현 — Kafka 연동 후 활성화")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP}")
    logger.info("  Topics: stock.raw.us, stock.raw.kr")

    # Phase 3 구현 예시:
    # from core.stock_fetcher import fetch_us_stocks, fetch_kr_stocks
    # from core.stock_categories import get_all_us_tickers, get_all_kr_tickers
    # from confluent_kafka import Producer
    #
    # producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    # us_data = fetch_us_stocks(get_all_us_tickers())
    # for ticker, df in us_data.items():
    #     producer.produce("stock.raw.us", key=ticker, value=df.to_json())
    # producer.flush()


if __name__ == "__main__":
    main()
