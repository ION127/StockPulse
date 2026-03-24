"""
Anomaly Detector 서비스 — Phase 3

역할:
  - Kafka Topic 'stock.raw.us', 'stock.raw.kr' 구독
  - Z-score + % 임계값으로 이상값 탐지
  - 이벤트 유형 자동 분류 (INDIVIDUAL / SECTOR / MARKET)
  - Kafka Topic 'anomaly.detected'에 이상값별로 발행

메시지 형식 (anomaly.detected):
  key   : ticker
  value : {
      ticker, date, bar_timestamp, return_pct, zscore, close_price, volume,
      direction, event_type, sector,
      sector_peer_count, moving_sector_count, is_recent
  }

환경변수:
  ANOMALY_THRESHOLD_PERCENT  % 임계값 (장중 1분봉 기준 기본 1.5)
  ANOMALY_ZSCORE_THRESHOLD   Z-score 임계값 (기본 3.0)
  INTRADAY_RECENT_MINUTES    0 이면 날짜 기반(is_recent), 양수면 bar_timestamp 기준 N분 이내만 처리
"""

import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta

import pandas as pd
from confluent_kafka import Consumer, KafkaError, Producer
from prometheus_client import Counter, start_http_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("anomaly-detector")

KAFKA_BOOTSTRAP          = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
THRESHOLD_PCT            = float(os.getenv("ANOMALY_THRESHOLD_PERCENT", "1.5"))
THRESHOLD_Z              = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0"))
INTRADAY_RECENT_MINUTES  = int(os.getenv("INTRADAY_RECENT_MINUTES", "5"))
USE_ADAPTIVE             = os.getenv("USE_ADAPTIVE_DETECTION", "false").lower() == "true"
GROUP_ID                 = "anomaly-detector-group"

# ── Prometheus 메트릭 ─────────────────────────────────────────────────────────
ANOMALY_COUNTER = Counter(
    "anomaly_detected_total",
    "탐지된 이상값 총 건수",
    ["event_type", "direction", "market"],
)
KAFKA_ERROR_COUNTER = Counter(
    "anomaly_detector_kafka_errors_total",
    "Kafka 오류 건수",
)
PROCESS_ERROR_COUNTER = Counter(
    "anomaly_detector_process_errors_total",
    "메시지 처리 오류 건수",
)

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("종료 신호 수신 — 루프 종료 중")
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _parse_bar_ts(ts_str: str) -> datetime:
    """bar_timestamp 문자열을 datetime으로 변환. 파싱 실패 시 datetime.min 반환."""
    try:
        return datetime.fromisoformat(ts_str)
    except Exception:
        return datetime.min


def _restore_dataframes(stocks_raw: dict) -> dict:
    """JSON dict → {ticker: DataFrame(OHLCV)} 복원"""
    result = {}
    for ticker, rows in stocks_raw.items():
        if not rows:
            continue
        df = pd.DataFrame.from_dict(rows, orient="index")
        df.index = pd.to_datetime(df.index)
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        result[ticker] = df
    return result


def _delivery_report(err, msg):
    if err:
        logger.error(f"전송 실패 [{msg.topic()}]: {err}")


def main():
    # Prometheus /metrics HTTP 서버 (백그라운드 스레드)
    start_http_server(8001)
    logger.info("[anomaly-detector] Prometheus metrics 서버 시작 — port 8001")

    logger.info(
        f"[anomaly-detector] 시작 | Kafka: {KAFKA_BOOTSTRAP} "
        f"| 임계값: {THRESHOLD_PCT}%, {THRESHOLD_Z}σ"
    )

    try:
        from core.stock_categories import STOCK_CATEGORIES
        from core.stock_fetcher import classify_event_type, detect_anomalies, detect_anomalies_adaptive
    except ImportError as e:
        logger.error(f"core 모듈 임포트 실패: {e}")
        sys.exit(1)

    detect_fn = detect_anomalies_adaptive if USE_ADAPTIVE else detect_anomalies
    logger.info(f"탐지 모드: {'적응형 (adaptive)' if USE_ADAPTIVE else '고정 임계값'}")

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
        "fetch.message.max.bytes": 10_485_760,
        "max.partition.fetch.bytes": 10_485_760,
    })
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
    })

    consumer.subscribe(["stock.raw.us", "stock.raw.kr"])
    logger.info("구독 시작: stock.raw.us, stock.raw.kr")

    try:
        while _running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Kafka 오류: {msg.error()}")
                KAFKA_ERROR_COUNTER.inc()
                continue

            try:
                data = json.loads(msg.value())
                market = data.get("market", "us")
                stocks_raw = data.get("stocks", {})

                if not stocks_raw:
                    logger.warning(f"[{market.upper()}] 빈 배치 메시지 — 건너뜀")
                    continue

                stock_data = _restore_dataframes(stocks_raw)
                logger.info(f"[{market.upper()}] {len(stock_data)}개 종목 이상값 탐지 중")

                anomalies = detect_fn(stock_data, THRESHOLD_PCT, THRESHOLD_Z)

                # 장중 모드: bar_timestamp 기준으로 최근 N분 이내만 처리
                # 일별 모드: is_recent(5일 이내) 기준
                if INTRADAY_RECENT_MINUTES > 0:
                    cutoff = datetime.now() - timedelta(minutes=INTRADAY_RECENT_MINUTES)
                    recent = [
                        a for a in anomalies
                        if _parse_bar_ts(a.get("bar_timestamp", "")) >= cutoff
                    ]
                else:
                    recent = [a for a in anomalies if a.get("is_recent")]

                if not recent:
                    logger.info(f"[{market.upper()}] 최근 이상값 없음")
                    continue

                classified = classify_event_type(recent, STOCK_CATEGORIES)
                logger.info(f"[{market.upper()}] 이상값 {len(classified)}건 감지")

                for anomaly in classified:
                    payload = {**anomaly, "date": str(anomaly["date"])}
                    producer.produce(
                        "anomaly.detected",
                        key=anomaly["ticker"],
                        value=json.dumps(payload, default=str),
                        callback=_delivery_report,
                    )

                producer.flush()
                logger.info(f"anomaly.detected {len(classified)}건 발행")

                for anomaly in classified:
                    ANOMALY_COUNTER.labels(
                        event_type=anomaly.get("event_type", "UNKNOWN"),
                        direction=anomaly.get("direction", "UNKNOWN"),
                        market=market,
                    ).inc()

            except Exception as e:
                logger.error(f"메시지 처리 오류: {e}", exc_info=True)
                PROCESS_ERROR_COUNTER.inc()

    finally:
        consumer.close()
        logger.info("[anomaly-detector] 종료")


if __name__ == "__main__":
    main()
