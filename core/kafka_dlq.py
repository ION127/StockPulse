"""
Kafka Dead Letter Queue (DLQ) 헬퍼

처리 실패 메시지를 `{original_topic}.dlq` 토픽에 보존.

DLQ 메시지 형식:
  {
    "original_topic": "news.fetched",
    "error":          "...",
    "failed_at":      "2026-03-20T10:00:00",
    "original_value": "{ ... 원본 메시지 ... }"
  }

재처리 방법:
  DLQ 토픽을 구독해 메시지를 원본 토픽으로 다시 발행하면 됨.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MAX_RETRIES = 3  # 이 횟수 초과 시 DLQ로 이동


def get_retry_count(msg) -> int:
    """Kafka 메시지 헤더에서 retry_count를 읽어 반환 (없으면 0)."""
    try:
        headers = dict(msg.headers() or [])
        raw = headers.get(b"retry_count") or headers.get("retry_count", b"0")
        return int(raw)
    except (ValueError, TypeError):
        return 0


def send_to_dlq(
    producer,
    original_topic: str,
    original_value: bytes,
    original_key: bytes | None,
    error: Exception,
) -> None:
    """
    실패 메시지를 DLQ 토픽으로 이동.
    DLQ 토픽명: {original_topic}.dlq
    """
    dlq_topic = f"{original_topic}.dlq"
    envelope = {
        "original_topic": original_topic,
        "error":          str(error),
        "failed_at":      datetime.now(timezone.utc).isoformat(),
        "original_value": original_value.decode("utf-8", errors="replace"),
    }
    try:
        producer.produce(
            dlq_topic,
            key=original_key,
            value=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        )
        producer.flush()
        logger.warning(
            f"[DLQ] '{original_topic}' → '{dlq_topic}' 이동 완료 | 오류: {error}"
        )
    except Exception as publish_err:
        logger.error(f"[DLQ] DLQ 발행 실패 — 메시지 유실 가능성 있음: {publish_err}")
