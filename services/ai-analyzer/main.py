"""
AI Analyzer 서비스 — Phase 3

역할:
  - Kafka Topic 'news.fetched' 구독
  - Gemini 2.5 Flash로 한/영 이상값 원인 분석
  - Gemini Rate Limit 대응: 분당 15회 제한 → 5초 간격 자동 조절
  - Kafka Topic 'analysis.completed'에 발행

메시지 형식 (analysis.completed):
  key   : ticker
  value : {
      ...news.fetched 필드 전부 (news_text 제거),
      "analysis_ko" : str,
      "analysis_en" : str
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
logger = logging.getLogger("ai-analyzer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROUP_ID = "ai-analyzer-group"

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
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY 미설정 — 분석 결과는 오류 메시지로 대체됩니다")

    logger.info(
        f"[ai-analyzer] 시작 | Kafka: {KAFKA_BOOTSTRAP} "
        f"| Gemini: {'설정됨' if GEMINI_API_KEY else '미설정'}"
    )

    try:
        from core.ai_analyzer import analyze_anomaly
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

    consumer.subscribe(["news.fetched"])
    logger.info("구독 시작: news.fetched")

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
                data = json.loads(msg.value())
                ticker = data["ticker"]
                logger.info(f"AI 분석 중: {ticker}")

                analysis = analyze_anomaly(
                    ticker=ticker,
                    category=data.get("sector", ""),
                    return_pct=data["return_pct"],
                    direction=data["direction"],
                    date=data.get("date", ""),
                    close_price=data.get("close_price", 0) or 0,
                    news_text=data.get("news_text", ""),
                    event_type=data.get("event_type", "INDIVIDUAL"),
                    sector_peer_count=data.get("sector_peer_count", 1) or 1,
                    moving_sector_count=data.get("moving_sector_count", 1) or 1,
                )

                # news_text는 프롬프트용이므로 downstream에 전달 불필요
                payload = {k: v for k, v in data.items() if k != "news_text"}
                payload["analysis_ko"] = analysis.get("ko", "")
                payload["analysis_en"] = analysis.get("en", "")

                producer.produce(
                    "analysis.completed",
                    key=ticker,
                    value=json.dumps(payload, ensure_ascii=False),
                    callback=_delivery_report,
                )
                producer.flush()

                logger.info(f"analysis.completed 발행: {ticker}")

            except Exception as e:
                logger.error(f"메시지 처리 오류: {e}", exc_info=True)

    finally:
        consumer.close()
        logger.info("[ai-analyzer] 종료")


if __name__ == "__main__":
    main()
