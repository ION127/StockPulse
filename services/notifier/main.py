"""
Notifier 서비스 — Phase 3

역할:
  - Kafka Topic 'analysis.completed' 구독
  - 섹터/이벤트 유형 필터링
  - Slack Incoming Webhook으로 분석 결과 발송

환경변수:
  KAFKA_BOOTSTRAP_SERVERS  Kafka 브로커 주소
  SLACK_WEBHOOK_URL        Slack Incoming Webhook URL (없으면 로그로만 출력)
  NOTIFY_SECTORS           콤마 구분 섹터 필터 (빈 값 = 전체 허용)
  NOTIFY_EVENT_TYPES       콤마 구분 이벤트 유형 (기본 INDIVIDUAL,SECTOR,MARKET)
"""

import json
import logging
import os
import signal

import time

import requests
from confluent_kafka import Consumer, KafkaError, Producer

# DLQ 헬퍼
try:
    import sys as _sys, os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from core.kafka_dlq import send_to_dlq
    _DLQ_AVAILABLE = True
except ImportError:
    _DLQ_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("notifier")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
NOTIFY_SECTORS = [s.strip() for s in os.getenv("NOTIFY_SECTORS", "").split(",") if s.strip()]
NOTIFY_EVENT_TYPES = [
    t.strip()
    for t in os.getenv("NOTIFY_EVENT_TYPES", "INDIVIDUAL,SECTOR,MARKET").split(",")
    if t.strip()
]
GROUP_ID = "notifier-group"

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("종료 신호 수신 — 루프 종료 중")
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _format_message(data: dict) -> str:
    ticker = data.get("ticker", "")
    ret = data.get("return_pct", 0.0)
    direction = data.get("direction", "")
    event_type = data.get("event_type", "INDIVIDUAL")
    sector = data.get("sector", "")
    date = data.get("date", "")
    analysis_ko = data.get("analysis_ko", "")
    peer_count = data.get("sector_peer_count", 1)
    sector_count = data.get("moving_sector_count", 1)

    event_emoji = {"INDIVIDUAL": "📊", "SECTOR": "🏭", "MARKET": "🌍"}.get(event_type, "📈")
    dir_emoji = "🚀" if direction == "급등" else "📉"

    lines = [
        f"{event_emoji} *{ticker}*  {dir_emoji} `{ret:+.2f}%`  [{event_type}]",
        f"📅 {date}  |  🏷️ {sector}",
        f"👥 동시 이동: 섹터 내 {peer_count}종목, {sector_count}개 섹터",
    ]

    if analysis_ko:
        # 첫 500자만 포함
        summary = analysis_ko[:500].replace("\n", " ")
        lines.append(f"\n> {summary}…")

    return "\n".join(lines)


_SLACK_MAX_RETRIES = 3
_SLACK_RETRY_DELAY = 5  # 초


def _send_slack(text: str) -> bool:
    """
    Slack 웹훅으로 메시지 전송. 최대 3회 재시도.
    성공 시 True, 최종 실패 시 False 반환.
    """
    if not SLACK_WEBHOOK:
        logger.info(f"[Slack 미설정 — 로그 출력]\n{text}")
        return True

    for attempt in range(_SLACK_MAX_RETRIES):
        try:
            resp = requests.post(
                SLACK_WEBHOOK,
                json={"text": text},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("Slack 알림 발송 완료")
            return True
        except Exception as e:
            if attempt < _SLACK_MAX_RETRIES - 1:
                logger.warning(
                    f"Slack 알림 실패 ({attempt + 1}/{_SLACK_MAX_RETRIES}): {e} "
                    f"— {_SLACK_RETRY_DELAY}초 후 재시도"
                )
                time.sleep(_SLACK_RETRY_DELAY)
            else:
                logger.error(f"Slack 알림 최종 실패 ({_SLACK_MAX_RETRIES}회 시도): {e}")
    return False


def main():
    logger.info(
        f"[notifier] 시작 | Kafka: {KAFKA_BOOTSTRAP} "
        f"| Slack: {'설정됨' if SLACK_WEBHOOK else '미설정'}"
    )
    logger.info(
        f"  필터 섹터: {NOTIFY_SECTORS or '전체'} "
        f"| 이벤트 유형: {NOTIFY_EVENT_TYPES}"
    )

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
    })
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

    consumer.subscribe(["analysis.completed"])
    logger.info("구독 시작: analysis.completed")

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
                ticker = data.get("ticker", "")
                event_type = data.get("event_type", "INDIVIDUAL")
                sector = data.get("sector", "")

                # 이벤트 유형 필터
                if NOTIFY_EVENT_TYPES and event_type not in NOTIFY_EVENT_TYPES:
                    logger.debug(f"이벤트 유형 필터 제외: {ticker} ({event_type})")
                    continue

                # 섹터 필터
                if NOTIFY_SECTORS and sector not in NOTIFY_SECTORS:
                    logger.debug(f"섹터 필터 제외: {ticker} ({sector})")
                    continue

                text = _format_message(data)
                success = _send_slack(text)

                # Slack 최종 실패 → DLQ 보존
                if not success and _DLQ_AVAILABLE:
                    send_to_dlq(
                        producer,
                        "analysis.completed",
                        msg.value(),
                        msg.key(),
                        RuntimeError(f"Slack 알림 {_SLACK_MAX_RETRIES}회 실패"),
                    )

            except Exception as e:
                logger.error(f"메시지 처리 오류: {e}", exc_info=True)

    finally:
        consumer.close()
        logger.info("[notifier] 종료")


if __name__ == "__main__":
    main()
