"""
Anomaly Detector 서비스 — Phase 3 (Kafka 연동 예정)

현재: stub (Phase 3에서 구현)
Phase 3 역할:
  - Kafka Topic 'stock.raw.us', 'stock.raw.kr' 구독
  - Z-score + % 임계값으로 이상값 탐지
  - 이벤트 유형 분류 (INDIVIDUAL / SECTOR / MARKET)
  - Kafka Topic 'anomaly.detected'에 발행

환경변수:
  - KAFKA_BOOTSTRAP_SERVERS
  - ANOMALY_THRESHOLD_PERCENT (기본 8.0)
  - ANOMALY_ZSCORE_THRESHOLD (기본 3.0)
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
THRESHOLD_PCT = float(os.getenv("ANOMALY_THRESHOLD_PERCENT", "8.0"))
THRESHOLD_Z = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0"))


def main():
    logger.info("[anomaly-detector] Phase 3 미구현 — Kafka 연동 후 활성화")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP}")
    logger.info(f"  Thresholds: pct={THRESHOLD_PCT}%, z={THRESHOLD_Z}")
    logger.info("  Subscribe: stock.raw.us, stock.raw.kr")
    logger.info("  Publish:   anomaly.detected")

    # Phase 3 구현 예시:
    # from core.stock_fetcher import detect_anomalies, classify_event_type
    # from core.stock_categories import STOCK_CATEGORIES
    # from confluent_kafka import Consumer, Producer
    #
    # consumer = Consumer({...})
    # consumer.subscribe(["stock.raw.us", "stock.raw.kr"])
    # producer = Producer({...})
    # while True:
    #     msg = consumer.poll(1.0)
    #     anomalies = detect_anomalies(json.loads(msg.value()), THRESHOLD_PCT, THRESHOLD_Z)
    #     for a in anomalies:
    #         producer.produce("anomaly.detected", value=json.dumps(a))


if __name__ == "__main__":
    main()
