"""
Stock Collector 서비스 — 미국 1분봉 (Phase 3 intraday)

역할:
  - yfinance로 미국 주식 1분봉 데이터 수집 (최근 5일치)
  - Kafka Topic 'stock.raw.us'에 배치로 발행
  - 60초마다 반복 실행 (장중 상시 모니터링)

※ 한국 주식 실시간은 kiwoom-bridge 서비스가 담당
  (services/kiwoom-bridge/main.py — Windows 네이티브 실행)

메시지 형식 (stock.raw.us):
  key   : "batch"
  value : {
      "market"    : "us",
      "timestamp" : ISO8601,
      "stocks"    : {
          "<ticker>": {
              "<YYYY-MM-DD HH:MM:SS>": {
                  "Open": float, "High": float, "Low": float,
                  "Close": float, "Volume": int
              }, ...
          }, ...
      }
  }

환경변수:
  KAFKA_BOOTSTRAP_SERVERS  Kafka 브로커 주소 (기본 kafka:9092)
  STOCK_INTERVAL           yfinance interval (기본 1m)
  STOCK_PERIOD             yfinance period (기본 5d, 1m 기준 최대 7d)
  COLLECT_INTERVAL_SECONDS 수집 주기 초 (기본 60)
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("stock-collector")

KAFKA_BOOTSTRAP      = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
STOCK_INTERVAL       = os.getenv("STOCK_INTERVAL", "1m")
STOCK_PERIOD         = os.getenv("STOCK_PERIOD", "5d")
COLLECT_INTERVAL_SEC = int(os.getenv("COLLECT_INTERVAL_SECONDS", "60"))

_running = True


def _handle_signal(sig, frame):
    global _running
    logger.info("종료 신호 수신 — 루프 종료 중")
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _build_producer():
    from confluent_kafka import Producer
    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "message.max.bytes": 10_485_760,   # 10 MB
        "queue.buffering.max.messages": 100,
    })


def _delivery_report(err, msg):
    if err:
        logger.error(f"전송 실패 [{msg.topic()}]: {err}")
    else:
        logger.debug(f"발행 완료 [{msg.topic()} p{msg.partition()}] {len(msg.value())} bytes")


def _df_to_dict(df) -> dict:
    """DataFrame → JSON 직렬화 가능한 dict (datetime key)"""
    df_copy = df.copy()
    df_copy.index = df_copy.index.astype(str)
    return df_copy.to_dict(orient="index")


def publish_batch(producer, topic: str, market: str, stock_data: dict) -> int:
    """stock_data({ticker: DataFrame})를 하나의 Kafka 메시지로 발행."""
    serialized = {ticker: _df_to_dict(df) for ticker, df in stock_data.items()}
    payload = {
        "market":    market,
        "timestamp": datetime.now().isoformat(),
        "stocks":    serialized,
    }
    value = json.dumps(payload, default=str).encode("utf-8")
    producer.produce(topic, key="batch", value=value, callback=_delivery_report)
    producer.flush()
    logger.info(f"[{topic}] {len(serialized)}개 종목 발행 완료 ({len(value)/1024:.1f} KB)")
    return len(serialized)


def main():
    logger.info(
        f"[stock-collector] 시작 | Kafka: {KAFKA_BOOTSTRAP} "
        f"| interval={STOCK_INTERVAL} period={STOCK_PERIOD} "
        f"| 수집주기={COLLECT_INTERVAL_SEC}s"
    )
    logger.info("※ 한국 주식 실시간은 kiwoom-bridge 서비스가 별도 담당")

    try:
        from core.stock_categories import get_all_us_tickers
        from core.stock_fetcher import fetch_us_stocks_intraday
    except ImportError as e:
        logger.error(f"core 모듈 임포트 실패: {e}")
        sys.exit(1)

    producer = _build_producer()
    us_tickers = get_all_us_tickers()
    logger.info(f"미국 주식 {len(us_tickers)}개 종목 모니터링")

    while _running:
        loop_start = time.time()
        try:
            us_data = fetch_us_stocks_intraday(
                us_tickers,
                interval=STOCK_INTERVAL,
                period=STOCK_PERIOD,
            )
            if us_data:
                publish_batch(producer, "stock.raw.us", "us", us_data)
            else:
                logger.warning("미국 주식 수집 결과 없음 — stock.raw.us 발행 생략")

        except Exception as e:
            logger.error(f"수집/발행 오류: {e}", exc_info=True)

        # 다음 수집까지 대기 (처리 시간 제외)
        elapsed = time.time() - loop_start
        sleep_sec = max(0, COLLECT_INTERVAL_SEC - elapsed)
        if _running and sleep_sec > 0:
            logger.debug(f"다음 수집까지 {sleep_sec:.1f}초 대기")
            time.sleep(sleep_sec)

    logger.info("[stock-collector] 종료")


if __name__ == "__main__":
    main()
