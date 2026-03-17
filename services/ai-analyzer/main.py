"""
AI Analyzer 서비스 — Phase 3 (Kafka 연동 예정)

현재: stub (Phase 3에서 구현)
Phase 3 역할:
  - Kafka Topic 'news.fetched' 구독
  - Gemini 2.5 Flash로 한/영 이상값 원인 분석
  - Gemini Rate Limit 대응: 5초 간격, 자동 재시도
  - Kafka Topic 'analysis.completed'에 발행

환경변수:
  - KAFKA_BOOTSTRAP_SERVERS
  - GEMINI_API_KEY
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def main():
    logger.info("[ai-analyzer] Phase 3 미구현 — Kafka 연동 후 활성화")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP}")
    logger.info(f"  Gemini API Key: {'설정됨' if GEMINI_API_KEY else '미설정'}")
    logger.info("  Subscribe: news.fetched")
    logger.info("  Publish:   analysis.completed")

    # Phase 3 구현 예시:
    # from core.ai_analyzer import analyze_anomaly
    # from confluent_kafka import Consumer, Producer
    #
    # consumer = Consumer({...})
    # consumer.subscribe(["news.fetched"])
    # while True:
    #     msg = consumer.poll(1.0)
    #     data = json.loads(msg.value())
    #     analysis = analyze_anomaly(data["ticker"], data["sector"], ...)
    #     producer.produce("analysis.completed", value=json.dumps({**data, "analysis": analysis}))


if __name__ == "__main__":
    main()
