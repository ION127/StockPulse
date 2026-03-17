"""
Notifier 서비스 — Phase 3 (Kafka 연동 예정)

현재: stub (Phase 3에서 구현)
Phase 3 역할:
  - Kafka Topic 'analysis.completed' 구독
  - 슬랙 / 이메일로 이상값 분석 결과 발송
  - 채널별 필터링 (섹터, 이벤트 유형)

환경변수:
  - KAFKA_BOOTSTRAP_SERVERS
  - SLACK_WEBHOOK_URL (슬랙 Incoming Webhook)
  - NOTIFY_SECTORS (콤마 구분, 빈 값 = 전체)
  - NOTIFY_EVENT_TYPES (INDIVIDUAL,SECTOR,MARKET)
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")


def main():
    logger.info("[notifier] Phase 3 미구현 — Kafka 연동 후 활성화")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP}")
    logger.info(f"  Slack Webhook: {'설정됨' if SLACK_WEBHOOK else '미설정'}")
    logger.info("  Subscribe: analysis.completed")

    # Phase 3 구현 예시:
    # import requests
    # from confluent_kafka import Consumer
    #
    # consumer = Consumer({...})
    # consumer.subscribe(["analysis.completed"])
    # while True:
    #     msg = consumer.poll(1.0)
    #     data = json.loads(msg.value())
    #     text = f"*{data['ticker']}* {data['return_pct']:+.2f}% [{data['event_type']}]\n{data['analysis']['ko'][:500]}"
    #     requests.post(SLACK_WEBHOOK, json={"text": text})


if __name__ == "__main__":
    main()
